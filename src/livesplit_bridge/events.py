from __future__ import annotations

import time
from collections.abc import Iterator
from math import ceil
from typing import Any, Self

import zmq

from .client import BridgeClientError, BridgeEventStreamLostError, BridgeTimeoutError
from .protocol import common_pb2

DEFAULT_EVENT_ENDPOINT = "tcp://127.0.0.1:54001"

_monotonic = time.monotonic


class BridgeEventSubscriber(Iterator[common_pb2.BridgeEvent]):
    """Synchronous ZeroMQ SUB subscriber for LiveSplit.Bridge events.

    This class is single-threaded: it must only be used from a single thread at a time.
    """

    def __init__(
        self,
        event_endpoint: str = DEFAULT_EVENT_ENDPOINT,
        *,
        receive_timeout_ms: int | None = None,
        heartbeat_timeout_ms: int | None = None,
        context: Any | None = None,
    ) -> None:
        if receive_timeout_ms is not None and receive_timeout_ms < 0:
            raise ValueError("receive_timeout_ms must be non-negative or None")
        if heartbeat_timeout_ms is not None and heartbeat_timeout_ms < 0:
            raise ValueError("heartbeat_timeout_ms must be non-negative or None")
        self.event_endpoint = event_endpoint
        self.receive_timeout_ms = receive_timeout_ms
        self.heartbeat_timeout_ms = heartbeat_timeout_ms
        self._context = context if context is not None else zmq.Context()
        self._owns_context = context is None
        self._socket: Any | None = None
        self._closed = False
        self._heartbeat_deadline: float | None = None
        socket = self._context.socket(zmq.SUB)
        try:
            socket.setsockopt(zmq.LINGER, 0)
            socket.setsockopt(zmq.SUBSCRIBE, b"")
            socket.connect(event_endpoint)
        except Exception:
            try:
                socket.close()
            finally:
                if self._owns_context:
                    self._context.term()
            raise
        self._socket = socket
        if self.heartbeat_timeout_ms is not None:
            self._heartbeat_deadline = _monotonic() + self.heartbeat_timeout_ms / 1000

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        socket = self._socket
        self._socket = None
        try:
            if socket is not None:
                socket.close()
        finally:
            if self._owns_context:
                self._context.term()

    def __enter__(self) -> Self:
        if self._closed:
            raise BridgeClientError("Event subscriber is closed")
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def receive(self, *, timeout_ms: int | None = None) -> common_pb2.BridgeEvent:
        if self._closed or self._socket is None:
            raise BridgeClientError("Event subscriber is closed")
        effective_timeout = self.receive_timeout_ms if timeout_ms is None else timeout_ms
        if effective_timeout is not None and effective_timeout < 0:
            raise ValueError("timeout_ms must be non-negative or None")
        socket = self._socket
        if self.heartbeat_timeout_ms is not None:
            return self._receive_with_heartbeat(
                socket, effective_timeout, self.heartbeat_timeout_ms
            )
        if effective_timeout is not None:
            if not socket.poll(effective_timeout, zmq.POLLIN):
                raise BridgeTimeoutError(
                    f"Event receive timed out after {effective_timeout} ms ({self.event_endpoint})"
                )
        return common_pb2.BridgeEvent.FromString(socket.recv())

    def _receive_with_heartbeat(
        self, socket: Any, effective_timeout: int | None, heartbeat_timeout_ms: int
    ) -> common_pb2.BridgeEvent:
        deadline = self._heartbeat_deadline
        assert deadline is not None
        now = _monotonic()
        if now >= deadline:
            self._raise_event_stream_lost(heartbeat_timeout_ms)
        remaining_ms = (deadline - now) * 1000
        heartbeat_side = True
        poll_timeout = remaining_ms
        if effective_timeout is not None and effective_timeout < remaining_ms:
            poll_timeout = effective_timeout
            heartbeat_side = False
        if not socket.poll(ceil(poll_timeout), zmq.POLLIN):
            if heartbeat_side:
                self._raise_event_stream_lost(heartbeat_timeout_ms)
            raise BridgeTimeoutError(
                f"Event receive timed out after {effective_timeout} ms ({self.event_endpoint})"
            )
        event = common_pb2.BridgeEvent.FromString(socket.recv())
        received_at = _monotonic()
        if received_at >= deadline:
            self._raise_event_stream_lost(heartbeat_timeout_ms)
        if event.type == common_pb2.EVENT_HEARTBEAT:
            self._heartbeat_deadline = received_at + heartbeat_timeout_ms / 1000
        return event

    def _raise_event_stream_lost(self, heartbeat_timeout_ms: int) -> None:
        raise BridgeEventStreamLostError(
            "Event stream is no longer trustworthy because heartbeats are missing: "
            f"no heartbeat within {heartbeat_timeout_ms} ms ({self.event_endpoint})"
        )

    def __next__(self) -> common_pb2.BridgeEvent:
        return self.receive()
