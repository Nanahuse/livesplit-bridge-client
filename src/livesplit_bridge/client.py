from __future__ import annotations

from collections.abc import Iterator
from typing import Self

from .events import DEFAULT_EVENT_ENDPOINT, BridgeEventSubscriber
from .protocol import bridge_pb2, common_pb2, run_pb2
from .rpc import DEFAULT_RPC_ENDPOINT, BridgeClientError, BridgeRpcClient


class BridgeClient(Iterator[common_pb2.BridgeEvent]):
    """Integrated synchronous client that combines RPC and event subscription.

    Owns a :class:`BridgeEventSubscriber` and a :class:`BridgeRpcClient`, each backed by
    its own WebSocket connection. The subscriber is created first, then the RPC client.

    This class is single-threaded: it must only be used from a single thread at a time.
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
        try:
            self._events = BridgeEventSubscriber(event_endpoint)
            self._rpc = BridgeRpcClient(
                rpc_endpoint,
                response_timeout_ms=response_timeout_ms,
            )
        except Exception:
            events = self._events
            rpc = self._rpc
            self._events = None
            self._rpc = None
            try:
                if events is not None:
                    events.close()
            finally:
                if rpc is not None:
                    rpc.close()
            raise

    def _ensure_open(self) -> None:
        if self._closed:
            raise BridgeClientError("Client is closed")

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
        """Session ID from the most recent RPC response, or zero before the first RPC."""
        return self.rpc.session_id

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        events = self._events
        rpc = self._rpc
        self._events = None
        self._rpc = None
        try:
            if events is not None:
                events.close()
        finally:
            if rpc is not None:
                rpc.close()

    def __enter__(self) -> Self:
        self._ensure_open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def request(self, request: bridge_pb2.Request) -> bridge_pb2.Response:
        return self.rpc.request(request)

    def get_timer_state(self) -> common_pb2.TimerState:
        return self.rpc.get_timer_state()

    def get_run(self) -> run_pb2.RunState:
        return self.rpc.get_run()

    def get_attempt(self) -> common_pb2.AttemptState:
        return self.rpc.get_attempt()

    def get_context_state(self) -> common_pb2.ContextState:
        return self.rpc.get_context_state()

    def get_completed_count(self) -> common_pb2.CompletedCount:
        return self.rpc.get_completed_count()

    def timer_operation(
        self, operation: common_pb2.TimerOperationType
    ) -> common_pb2.OperationResponse:
        return self.rpc.timer_operation(operation)

    def game_time_operation(
        self, operation: common_pb2.GameTimeOperationType, *, ticks: int | None = None
    ) -> common_pb2.OperationResponse:
        return self.rpc.game_time_operation(operation, ticks=ticks)

    def start(self) -> common_pb2.OperationResponse:
        return self.rpc.start()

    def split(self) -> common_pb2.OperationResponse:
        return self.rpc.split()

    def skip(self) -> common_pb2.OperationResponse:
        return self.rpc.skip()

    def undo(self) -> common_pb2.OperationResponse:
        return self.rpc.undo()

    def reset(self) -> common_pb2.OperationResponse:
        return self.rpc.reset()

    def pause(self) -> common_pb2.OperationResponse:
        return self.rpc.pause()

    def resume(self) -> common_pb2.OperationResponse:
        return self.rpc.resume()

    def initialize_game_time(self) -> common_pb2.OperationResponse:
        return self.rpc.initialize_game_time()

    def set_game_time_ticks(self, ticks: int) -> common_pb2.OperationResponse:
        return self.rpc.set_game_time_ticks(ticks)

    def pause_game_time(self) -> common_pb2.OperationResponse:
        return self.rpc.pause_game_time()

    def resume_game_time(self) -> common_pb2.OperationResponse:
        return self.rpc.resume_game_time()

    def receive(self, *, timeout_ms: int | None = None) -> common_pb2.BridgeEvent | None:
        return self.events.receive(timeout_ms=timeout_ms)

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> common_pb2.BridgeEvent:
        return next(self.events)

    def reconnect(self) -> None:
        """Recreate the subscriber and RPC client on fresh WebSocket connections.

        A new subscriber is created first, then a new RPC client. On any failure the
        new resources are closed and the old resources are kept, so the
        caller can retry. After a successful switch the old subscriber and RPC client are
        closed (old events first, then old RPC); even if closing an old resource raises,
        the new resources remain current.

        This operation is not atomic across the event and RPC connections: the event
        WebSocket is connected before the next RPC completes, so event gaps or duplicates
        are not prevented, and the next response and subsequent events are not ordered
        relative to each other. Use ``session_id`` and ``event_sequence`` to reconcile on
        the caller side if required.
        """
        self._ensure_open()
        new_events = BridgeEventSubscriber(self._event_endpoint)
        new_rpc: BridgeRpcClient | None = None
        try:
            new_rpc = BridgeRpcClient(
                self._rpc_endpoint,
                response_timeout_ms=self._response_timeout_ms,
            )
        except Exception:
            try:
                if new_rpc is not None:
                    new_rpc.close()
            finally:
                new_events.close()
            raise

        old_events = self._events
        old_rpc = self._rpc
        self._events = new_events
        self._rpc = new_rpc
        try:
            if old_events is not None:
                old_events.close()
        finally:
            if old_rpc is not None:
                old_rpc.close()
