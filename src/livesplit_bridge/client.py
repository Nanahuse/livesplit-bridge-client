from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Self

import zmq

from .events import DEFAULT_EVENT_ENDPOINT, BridgeEventSubscriber
from .protocol import bridge_pb2, common_pb2
from .rpc import DEFAULT_RPC_ENDPOINT, BridgeClientError, BridgeRpcClient


class BridgeClient(Iterator[common_pb2.BridgeEvent]):
    """Integrated synchronous client that combines RPC and event subscription.

    Owns a single ZeroMQ context shared by a :class:`BridgeEventSubscriber` and a
    :class:`BridgeRpcClient`. The subscriber is created first, then the RPC client. When
    no ``context`` is supplied the client owns and terminates it; otherwise the caller
    keeps ownership.

    This class is single-threaded: it must only be used from a single thread at a time.
    """

    def __init__(
        self,
        rpc_endpoint: str = DEFAULT_RPC_ENDPOINT,
        event_endpoint: str = DEFAULT_EVENT_ENDPOINT,
        *,
        rpc_timeout_ms: int = 3000,
        receive_timeout_ms: int | None = None,
        heartbeat_timeout_ms: int | None = None,
        context: Any | None = None,
    ) -> None:
        self._event_endpoint = event_endpoint
        self._receive_timeout_ms = receive_timeout_ms
        self._heartbeat_timeout_ms = heartbeat_timeout_ms
        self._context = context if context is not None else zmq.Context()
        self._owns_context = context is None
        self._closed = False
        self._rpc: BridgeRpcClient | None = None
        self._events: BridgeEventSubscriber | None = None
        try:
            self._events = BridgeEventSubscriber(
                event_endpoint,
                receive_timeout_ms=receive_timeout_ms,
                heartbeat_timeout_ms=heartbeat_timeout_ms,
                context=self._context,
            )
            self._rpc = BridgeRpcClient(
                rpc_endpoint,
                timeout_ms=rpc_timeout_ms,
                context=self._context,
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
                try:
                    if rpc is not None:
                        rpc.close()
                finally:
                    if self._owns_context:
                        self._context.term()
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
            try:
                if rpc is not None:
                    rpc.close()
            finally:
                if self._owns_context:
                    self._context.term()

    def __enter__(self) -> Self:
        self._ensure_open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def request(self, request: bridge_pb2.Request) -> bridge_pb2.Response:
        return self.rpc.request(request)

    def attach(self) -> bridge_pb2.AttachResponse:
        return self.rpc.attach()

    def snapshot(self) -> common_pb2.TimerSnapshot:
        return self.rpc.snapshot()

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

    def receive(self, *, timeout_ms: int | None = None) -> common_pb2.BridgeEvent:
        return self.events.receive(timeout_ms=timeout_ms)

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> common_pb2.BridgeEvent:
        return self.receive()

    def resynchronize(self) -> common_pb2.TimerSnapshot:
        """Replace the SUB subscriber and return a fresh RPC snapshot.

        A new subscriber is created and installed as the current subscriber, the old
        subscriber is closed, then ``snapshot()`` is called. The new subscriber remains
        current if closing the old subscriber or retrieving the snapshot fails, so the
        caller can retry.

        This operation is not atomic across the PUB/SUB and RPC channels: event gaps or
        duplicates between the replaced subscriber and the RPC snapshot are not
        prevented, and the returned snapshot and subsequent events are not ordered
        relative to each other.
        """
        self._ensure_open()
        new_subscriber = BridgeEventSubscriber(
            self._event_endpoint,
            receive_timeout_ms=self._receive_timeout_ms,
            heartbeat_timeout_ms=self._heartbeat_timeout_ms,
            context=self._context,
        )
        old_subscriber = self._events
        assert old_subscriber is not None
        self._events = new_subscriber
        old_subscriber.close()
        rpc = self._rpc
        assert rpc is not None
        return rpc.snapshot()
