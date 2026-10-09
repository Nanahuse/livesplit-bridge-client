from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn, Self, TypeVar

from .events import (
    DEFAULT_EVENT_ENDPOINT,
    BridgeConnectionLostError,
    BridgeEventSubscriber,
)
from .protocol import bridge_pb2, common_pb2, run_pb2
from .rpc import (
    DEFAULT_RPC_ENDPOINT,
    BridgeClientError,
    BridgeProtocolError,
    BridgeReconnectRequiredError,
    BridgeResyncRequiredError,
    BridgeRpcClient,
)

_QueryResult = TypeVar("_QueryResult")


class BridgeRecoveryState(StrEnum):
    HEALTHY = "HEALTHY"
    RESYNC_REQUIRED = "RESYNC_REQUIRED"
    RECONNECT_REQUIRED = "RECONNECT_REQUIRED"


@dataclass(frozen=True, slots=True)
class BridgeSyncState:
    """A consistent set of Bridge query results from one runtime session."""

    session_id: int
    timer_state: common_pb2.TimerState
    attempt: common_pb2.AttemptState
    run: run_pb2.RunState
    context_state: common_pb2.ContextState
    completed_count: common_pb2.CompletedCount | None = None


def _synchronize_rpc(rpc: BridgeRpcClient, *, include_completed_count: bool) -> BridgeSyncState:
    session_id = 0

    def query(method: Callable[[], _QueryResult]) -> _QueryResult:
        nonlocal session_id
        try:
            result = method()
        except Exception as error:
            if rpc.session_change is not None:
                old, new = rpc.session_change
                raise BridgeReconnectRequiredError(
                    f"RPC session changed during synchronize(): {old} to {new}"
                ) from error
            raise
        if rpc.session_change is not None:
            old, new = rpc.session_change
            raise BridgeReconnectRequiredError(
                f"RPC session changed during synchronize(): {old} to {new}"
            )
        current_session_id = rpc.session_id
        if session_id and current_session_id != session_id:
            raise BridgeReconnectRequiredError(
                f"RPC session changed during synchronize(): {session_id} to {current_session_id}"
            )
        session_id = current_session_id
        return result

    timer_state = query(rpc.get_timer_state)
    attempt = query(rpc.get_attempt)
    run = query(rpc.get_run)
    context_state = query(rpc.get_context_state)
    completed_count = query(rpc.get_completed_count) if include_completed_count else None
    if session_id == 0:
        raise BridgeReconnectRequiredError("synchronize() did not receive a valid session")
    return BridgeSyncState(
        session_id=session_id,
        timer_state=timer_state,
        attempt=attempt,
        run=run,
        context_state=context_state,
        completed_count=completed_count,
    )


class BridgeClient(Iterator[common_pb2.BridgeEvent]):
    """Integrated synchronous client for queries, controls, and v3 events.

    This class is single-threaded and keeps event continuity and RPC session checks
    alongside its two low-level WebSocket clients.
    """

    def __init__(
        self,
        rpc_endpoint: str = DEFAULT_RPC_ENDPOINT,
        event_endpoint: str = DEFAULT_EVENT_ENDPOINT,
        *,
        response_timeout_ms: int = 3000,
    ) -> None:
        self._rpc_endpoint = rpc_endpoint
        self._event_endpoint = event_endpoint
        self._response_timeout_ms = response_timeout_ms
        self._closed = False
        self._rpc: BridgeRpcClient | None = None
        self._events: BridgeEventSubscriber | None = None
        self._known_rpc_session_id = 0
        self._event_session_id: int | None = None
        self._last_event_sequence: int | None = None
        self._recovery_state = BridgeRecoveryState.HEALTHY
        try:
            self._events = BridgeEventSubscriber(event_endpoint)
            self._rpc = BridgeRpcClient(
                rpc_endpoint,
                response_timeout_ms=response_timeout_ms,
            )
        except Exception:
            self._close_connections(self._events, self._rpc)
            self._events = None
            self._rpc = None
            raise

    @staticmethod
    def _close_connections(
        events: BridgeEventSubscriber | None, rpc: BridgeRpcClient | None
    ) -> None:
        for connection in (events, rpc):
            if connection is None:
                continue
            try:
                connection.close()
            except Exception:
                pass

    def _ensure_open(self) -> None:
        if self._closed:
            raise BridgeClientError("Client is closed")

    @property
    def recovery_state(self) -> BridgeRecoveryState:
        return self._recovery_state

    def _raise_resync(self, message: str) -> NoReturn:
        if self._recovery_state is not BridgeRecoveryState.RECONNECT_REQUIRED:
            self._recovery_state = BridgeRecoveryState.RESYNC_REQUIRED
        raise BridgeResyncRequiredError(message)

    def _raise_reconnect(self, message: str) -> NoReturn:
        self._recovery_state = BridgeRecoveryState.RECONNECT_REQUIRED
        raise BridgeReconnectRequiredError(message)

    def _ensure_healthy(self) -> None:
        if self._recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED:
            raise BridgeReconnectRequiredError("Reconnect is required before client operations")
        if self._recovery_state is BridgeRecoveryState.RESYNC_REQUIRED:
            raise BridgeResyncRequiredError("synchronize() is required before client operations")

    @property
    def rpc(self) -> BridgeRpcClient:
        self._ensure_open()
        rpc = self._rpc
        assert rpc is not None
        return rpc

    @property
    def events(self) -> BridgeEventSubscriber:
        self._ensure_open()
        events = self._events
        assert events is not None
        return events

    @property
    def session_id(self) -> int:
        """Session ID from the latest valid RPC response, or zero before one arrives."""
        return self.rpc.session_id

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        events, rpc = self._events, self._rpc
        self._events = None
        self._rpc = None
        self._close_connections(events, rpc)

    def __enter__(self) -> Self:
        self._ensure_open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _observe_rpc_session(self) -> None:
        rpc_session = self.rpc.session_id
        if rpc_session == 0:
            return
        if self.rpc.session_change is not None:
            previous, new = self.rpc.session_change
            self._raise_reconnect(f"RPC session changed from {previous} to {new}")
        if self._event_session_id is not None and self._event_session_id != rpc_session:
            self._raise_reconnect("RPC and Events sessions differ; reconnect() is required")
        if self._known_rpc_session_id not in (0, rpc_session):
            self._raise_reconnect(
                f"RPC session changed from {self._known_rpc_session_id} to {rpc_session}"
            )
        self._known_rpc_session_id = rpc_session

    def _handle_rpc_exception(self, rpc: BridgeRpcClient) -> None:
        if rpc.transport_reset:
            self._recovery_state = BridgeRecoveryState.RECONNECT_REQUIRED
            return
        self._observe_rpc_session()

    def request(self, request: bridge_pb2.Request) -> bridge_pb2.Response:
        self._ensure_open()
        self._ensure_healthy()
        rpc = self.rpc
        try:
            response = rpc.request(request)
        except Exception:
            self._handle_rpc_exception(rpc)
            raise
        self._observe_rpc_session()
        return response

    def get_timer_state(self) -> common_pb2.TimerState:
        return self.request(
            bridge_pb2.Request(get_timer_state=bridge_pb2.GetTimerStateRequest())
        ).get_timer_state.timer_state

    def get_run(self) -> run_pb2.RunState:
        return self.request(bridge_pb2.Request(get_run=bridge_pb2.GetRunRequest())).get_run.run

    def get_attempt(self) -> common_pb2.AttemptState:
        return self.request(
            bridge_pb2.Request(get_attempt=bridge_pb2.GetAttemptRequest())
        ).get_attempt.attempt

    def get_context_state(self) -> common_pb2.ContextState:
        return self.request(
            bridge_pb2.Request(get_context_state=bridge_pb2.GetContextStateRequest())
        ).get_context_state.context_state

    def get_completed_count(self) -> common_pb2.CompletedCount:
        return self.request(
            bridge_pb2.Request(get_completed_count=bridge_pb2.GetCompletedCountRequest())
        ).get_completed_count.completed_count

    def timer_operation(
        self, operation: common_pb2.TimerOperationType
    ) -> common_pb2.OperationResponse:
        return self.request(
            bridge_pb2.Request(
                timer_operation=bridge_pb2.TimerOperationRequest(operation=operation)
            )
        ).operation

    def game_time_operation(
        self, operation: common_pb2.GameTimeOperationType, *, ticks: int | None = None
    ) -> common_pb2.OperationResponse:
        operation_request = bridge_pb2.GameTimeOperationRequest(operation=operation)
        if ticks is not None:
            operation_request.ticks = ticks
        return self.request(bridge_pb2.Request(game_time_operation=operation_request)).operation

    def start(self) -> common_pb2.OperationResponse:
        return self.timer_operation(common_pb2.TIMER_START)

    def split(self) -> common_pb2.OperationResponse:
        return self.timer_operation(common_pb2.TIMER_SPLIT)

    def skip(self) -> common_pb2.OperationResponse:
        return self.timer_operation(common_pb2.TIMER_SKIP)

    def undo(self) -> common_pb2.OperationResponse:
        return self.timer_operation(common_pb2.TIMER_UNDO)

    def reset(self) -> common_pb2.OperationResponse:
        return self.timer_operation(common_pb2.TIMER_RESET)

    def pause(self) -> common_pb2.OperationResponse:
        return self.timer_operation(common_pb2.TIMER_PAUSE)

    def resume(self) -> common_pb2.OperationResponse:
        return self.timer_operation(common_pb2.TIMER_RESUME)

    def initialize_game_time(self) -> common_pb2.OperationResponse:
        return self.game_time_operation(common_pb2.INITIALIZE)

    def set_game_time_ticks(self, ticks: int) -> common_pb2.OperationResponse:
        return self.game_time_operation(common_pb2.SET, ticks=ticks)

    def pause_game_time(self) -> common_pb2.OperationResponse:
        return self.game_time_operation(common_pb2.GAME_TIME_PAUSE)

    def resume_game_time(self) -> common_pb2.OperationResponse:
        return self.game_time_operation(common_pb2.GAME_TIME_RESUME)

    def synchronize(self, *, include_completed_count: bool = False) -> BridgeSyncState:
        """Fetch a complete client snapshot and verify every response has one session."""
        self._ensure_open()
        if self._recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED:
            raise BridgeReconnectRequiredError(
                "synchronize() cannot recover a lost session; call reconnect()"
            )
        previous_session_id = self._known_rpc_session_id
        try:
            rpc = self.rpc
            state = _synchronize_rpc(rpc, include_completed_count=include_completed_count)
        except BridgeReconnectRequiredError:
            self._recovery_state = BridgeRecoveryState.RECONNECT_REQUIRED
            raise
        except Exception:
            self._handle_rpc_exception(self.rpc)
            raise
        if previous_session_id and previous_session_id != state.session_id:
            self._raise_reconnect(
                f"RPC session changed during synchronize(): {previous_session_id} "
                f"to {state.session_id}"
            )
        if self._event_session_id is not None and self._event_session_id != state.session_id:
            self._raise_reconnect("RPC and Events sessions differ; reconnect() is required")
        self._known_rpc_session_id = state.session_id
        self._last_event_sequence = None
        self._recovery_state = BridgeRecoveryState.HEALTHY
        return state

    def receive(self, *, timeout_ms: int | None = None) -> common_pb2.BridgeEvent | None:
        self._ensure_open()
        self._ensure_healthy()
        try:
            event = self.events.receive(timeout_ms=timeout_ms)
        except BridgeProtocolError:
            if self._recovery_state is not BridgeRecoveryState.RECONNECT_REQUIRED:
                self._recovery_state = BridgeRecoveryState.RESYNC_REQUIRED
            raise
        except BridgeConnectionLostError:
            self._recovery_state = BridgeRecoveryState.RECONNECT_REQUIRED
            raise
        if event is None:
            return None
        if event.session_id == 0:
            self._raise_reconnect("Bridge event has an invalid zero session ID")
        if self._known_rpc_session_id and event.session_id != self._known_rpc_session_id:
            self._raise_reconnect(
                f"Event session {event.session_id} does not match RPC session "
                f"{self._known_rpc_session_id}"
            )
        if self._event_session_id is not None and event.session_id != self._event_session_id:
            self._raise_reconnect(
                f"Event session changed from {self._event_session_id} to {event.session_id}"
            )
        if self._last_event_sequence is not None:
            expected = self._last_event_sequence + 1
            if event.event_sequence != expected:
                self._raise_resync(
                    f"Event sequence gap: expected {expected}, got {event.event_sequence}"
                )

        known_types = {
            common_pb2.EVENT_TIMER_STARTED,
            common_pb2.EVENT_TIMER_SPLIT,
            common_pb2.EVENT_TIMER_SKIPPED,
            common_pb2.EVENT_TIMER_UNDO,
            common_pb2.EVENT_TIMER_RESET,
            common_pb2.EVENT_TIMER_PHASE_CHANGED,
            common_pb2.EVENT_RUN_CHANGED,
            common_pb2.EVENT_CONTEXT_CHANGED,
        }
        if event.type not in known_types:
            self._raise_resync(f"Unknown Bridge event type: {event.type}")
        timer_event_types = {
            common_pb2.EVENT_TIMER_STARTED,
            common_pb2.EVENT_TIMER_SPLIT,
            common_pb2.EVENT_TIMER_SKIPPED,
            common_pb2.EVENT_TIMER_UNDO,
            common_pb2.EVENT_TIMER_RESET,
            common_pb2.EVENT_TIMER_PHASE_CHANGED,
        }
        if event.type in timer_event_types and not event.HasField("timer_state"):
            if self._recovery_state is not BridgeRecoveryState.RECONNECT_REQUIRED:
                self._recovery_state = BridgeRecoveryState.RESYNC_REQUIRED
            raise BridgeProtocolError(
                f"Timer event {event.type} is missing its required timer_state"
            )

        self._event_session_id = event.session_id
        self._last_event_sequence = event.event_sequence
        return event

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> common_pb2.BridgeEvent:
        while (event := self.receive()) is None:
            pass
        return event

    def reconnect(self, *, include_completed_count: bool = False) -> BridgeSyncState:
        """Replace both connections only after the new pair has synchronized."""
        self._ensure_open()
        new_events = BridgeEventSubscriber(self._event_endpoint)
        new_rpc: BridgeRpcClient | None = None
        try:
            new_rpc = BridgeRpcClient(
                self._rpc_endpoint,
                response_timeout_ms=self._response_timeout_ms,
            )
            state = _synchronize_rpc(new_rpc, include_completed_count=include_completed_count)
        except Exception:
            self._close_connections(new_events, new_rpc)
            raise

        old_events, old_rpc = self._events, self._rpc
        self._events, self._rpc = new_events, new_rpc
        self._known_rpc_session_id = state.session_id
        self._event_session_id = None
        self._last_event_sequence = None
        self._recovery_state = BridgeRecoveryState.HEALTHY
        self._close_connections(old_events, old_rpc)
        return state
