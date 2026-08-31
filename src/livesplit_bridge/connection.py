from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Self

import zmq

from .client import DEFAULT_RPC_ENDPOINT, BridgeClient, BridgeClientError
from .events import DEFAULT_EVENT_ENDPOINT, BridgeEventSubscriber
from .protocol import bridge_pb2, common_pb2


class BridgeConnection(Iterator[common_pb2.BridgeEvent]):
    """Integrated synchronous client that combines RPC and event subscription.

    Owns a single ZeroMQ context shared by a :class:`BridgeEventSubscriber` and a
    :class:`BridgeClient`. The subscriber is created first, then the RPC client. When no
    ``context`` is supplied the connection owns and terminates it; otherwise the caller
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
        self._client: BridgeClient | None = None
        self._subscriber: BridgeEventSubscriber | None = None
        try:
            self._subscriber = BridgeEventSubscriber(
                event_endpoint,
                receive_timeout_ms=receive_timeout_ms,
                heartbeat_timeout_ms=heartbeat_timeout_ms,
                context=self._context,
            )
            self._client = BridgeClient(
                rpc_endpoint,
                timeout_ms=rpc_timeout_ms,
                context=self._context,
            )
        except Exception:
            subscriber = self._subscriber
            client = self._client
            self._subscriber = None
            self._client = None
            try:
                if subscriber is not None:
                    subscriber.close()
            finally:
                try:
                    if client is not None:
                        client.close()
                finally:
                    if self._owns_context:
                        self._context.term()
            raise

    def _ensure_open(self) -> None:
        if self._closed:
            raise BridgeClientError("Connection is closed")

    @property
    def client(self) -> BridgeClient:
        self._ensure_open()
        client = self._client
        assert client is not None
        return client

    @property
    def subscriber(self) -> BridgeEventSubscriber:
        self._ensure_open()
        subscriber = self._subscriber
        assert subscriber is not None
        return subscriber

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        subscriber = self._subscriber
        client = self._client
        self._subscriber = None
        self._client = None
        try:
            if subscriber is not None:
                subscriber.close()
        finally:
            try:
                if client is not None:
                    client.close()
            finally:
                if self._owns_context:
                    self._context.term()

    def __enter__(self) -> Self:
        self._ensure_open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def request(self, request: bridge_pb2.Request) -> bridge_pb2.Response:
        return self.client.request(request)

    def attach(self) -> bridge_pb2.AttachResponse:
        return self.client.attach()

    def snapshot(self) -> common_pb2.TimerSnapshot:
        return self.client.snapshot()

    def timer_operation(
        self, operation: common_pb2.TimerOperationType
    ) -> common_pb2.OperationResponse:
        return self.client.timer_operation(operation)

    def game_time_operation(
        self, operation: common_pb2.GameTimeOperationType, *, ticks: int | None = None
    ) -> common_pb2.OperationResponse:
        return self.client.game_time_operation(operation, ticks=ticks)

    def start(self) -> common_pb2.OperationResponse:
        return self.client.start()

    def split(self) -> common_pb2.OperationResponse:
        return self.client.split()

    def skip(self) -> common_pb2.OperationResponse:
        return self.client.skip()

    def undo(self) -> common_pb2.OperationResponse:
        return self.client.undo()

    def reset(self) -> common_pb2.OperationResponse:
        return self.client.reset()

    def pause(self) -> common_pb2.OperationResponse:
        return self.client.pause()

    def resume(self) -> common_pb2.OperationResponse:
        return self.client.resume()

    def initialize_game_time(self) -> common_pb2.OperationResponse:
        return self.client.initialize_game_time()

    def set_game_time_ticks(self, ticks: int) -> common_pb2.OperationResponse:
        return self.client.set_game_time_ticks(ticks)

    def pause_game_time(self) -> common_pb2.OperationResponse:
        return self.client.pause_game_time()

    def resume_game_time(self) -> common_pb2.OperationResponse:
        return self.client.resume_game_time()

    def receive(self, *, timeout_ms: int | None = None) -> common_pb2.BridgeEvent:
        return self.subscriber.receive(timeout_ms=timeout_ms)

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
        old_subscriber = self._subscriber
        assert old_subscriber is not None
        self._subscriber = new_subscriber
        old_subscriber.close()
        client = self._client
        assert client is not None
        return client.snapshot()
