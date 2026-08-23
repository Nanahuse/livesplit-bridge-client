from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Self

import zmq
from google.protobuf.message import Message

from .client import BridgeClientError, BridgeTimeoutError
from .protocol import common_pb2

DEFAULT_EVENT_ENDPOINT = "tcp://127.0.0.1:54001"


class BridgeEventSubscriber(Iterator[Message]):
    """Synchronous ZeroMQ subscriber for LiveSplit.Bridge events."""

    def __init__(
        self,
        event_endpoint: str = DEFAULT_EVENT_ENDPOINT,
        *,
        timeout_ms: int | None = None,
        context: Any | None = None,
    ) -> None:
        if timeout_ms is not None and timeout_ms < 0:
            raise ValueError("timeout_ms must be non-negative or None")
        self.event_endpoint = event_endpoint
        self.timeout_ms = timeout_ms
        self._context = context if context is not None else zmq.Context()
        self._owns_context = context is None
        socket = self._context.socket(zmq.SUB)
        socket.setsockopt(zmq.LINGER, 0)
        socket.setsockopt(zmq.SUBSCRIBE, b"")
        socket.connect(event_endpoint)
        self._socket: Any | None = socket
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._owns_context:
            self._context.term()

    def __enter__(self) -> Self:
        if self._closed:
            raise BridgeClientError("Event subscriber is closed")
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def receive(self, *, timeout_ms: int | None = None) -> Any:
        if self._closed or self._socket is None:
            raise BridgeClientError("Event subscriber is closed")
        effective_timeout = self.timeout_ms if timeout_ms is None else timeout_ms
        if effective_timeout is not None:
            if effective_timeout < 0:
                raise ValueError("timeout_ms must be non-negative or None")
            if not self._socket.poll(effective_timeout, zmq.POLLIN):
                raise BridgeTimeoutError(
                    f"Event receive timed out after {effective_timeout} ms ({self.event_endpoint})"
                )
        return common_pb2.BridgeEvent.FromString(self._socket.recv())

    def __next__(self) -> Any:
        return self.receive()
