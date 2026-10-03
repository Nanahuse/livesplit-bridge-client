from __future__ import annotations

import time
from collections.abc import Iterator
from math import ceil
from typing import Any, NoReturn, Self

import websocket

from .protocol import common_pb2
from .rpc import BridgeClientError, BridgeProtocolError

DEFAULT_EVENT_ENDPOINT = "ws://127.0.0.1:54000/bridge/v1/events"

_monotonic = time.monotonic


class BridgeConnectionLostError(BridgeClientError):
    """Raised when the event stream connection is lost or heartbeats are missing."""


class BridgeEventSubscriber(Iterator[common_pb2.BridgeEvent]):
    """Synchronous WebSocket subscriber for LiveSplit.Bridge events.

    This class is single-threaded: it must only be used from a single thread at a time.
    """

    def __init__(
        self,
        event_endpoint: str = DEFAULT_EVENT_ENDPOINT,
        *,
        receive_timeout_ms: int | None = None,
        heartbeat_timeout_ms: int | None = None,
    ) -> None:
        if receive_timeout_ms is not None and receive_timeout_ms < 0:
            raise ValueError("receive_timeout_ms must be non-negative or None")
        if heartbeat_timeout_ms is not None and heartbeat_timeout_ms < 0:
            raise ValueError("heartbeat_timeout_ms must be non-negative or None")
        self.event_endpoint = event_endpoint
        self.receive_timeout_ms = receive_timeout_ms
        self.heartbeat_timeout_ms = heartbeat_timeout_ms
        self._socket: Any | None = None
        self._closed = False
        self._connection_lost_message: str | None = None
        self._heartbeat_deadline: float | None = None
        self._connect()
        if self.heartbeat_timeout_ms is not None:
            self._heartbeat_deadline = _monotonic() + self.heartbeat_timeout_ms / 1000

    def _connect(self) -> None:
        try:
            socket = websocket.create_connection(self.event_endpoint)
        except (OSError, websocket.WebSocketException) as error:
            raise BridgeClientError(
                f"Failed to connect to event endpoint {self.event_endpoint}: {error}"
            ) from error
        self._socket = socket

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        socket = self._socket
        self._socket = None
        if socket is not None:
            socket.close()

    def __enter__(self) -> Self:
        if self._closed:
            raise BridgeClientError("Event subscriber is closed")
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def receive(self, *, timeout_ms: int | None = None) -> common_pb2.BridgeEvent | None:
        if self._closed or self._socket is None:
            raise BridgeClientError("Event subscriber is closed")
        if self._connection_lost_message is not None:
            raise BridgeConnectionLostError(self._connection_lost_message)
        effective_timeout = self.receive_timeout_ms if timeout_ms is None else timeout_ms
        if effective_timeout is not None and effective_timeout < 0:
            raise ValueError("timeout_ms must be non-negative or None")
        socket = self._socket
        if self.heartbeat_timeout_ms is not None:
            return self._receive_with_heartbeat(
                socket, effective_timeout, self.heartbeat_timeout_ms
            )
        return self._recv_event(socket, effective_timeout)

    def _recv_event(self, socket: Any, wait_ms: int | None) -> common_pb2.BridgeEvent | None:
        socket.settimeout(None if wait_ms is None else wait_ms / 1000)
        try:
            payload = socket.recv()
        except websocket.WebSocketTimeoutException:
            return None
        except (websocket.WebSocketConnectionClosedException, OSError):
            self._connection_lost(f"Event connection closed by Bridge ({self.event_endpoint})")
        except websocket.WebSocketException as error:
            self._connection_lost(f"Event connection failed: {error} ({self.event_endpoint})")
        return self._decode_event(payload)

    def _receive_with_heartbeat(
        self, socket: Any, effective_timeout: int | None, heartbeat_timeout_ms: int
    ) -> common_pb2.BridgeEvent | None:
        deadline = self._heartbeat_deadline
        assert deadline is not None
        now = _monotonic()
        if now >= deadline:
            self._raise_heartbeat_timeout(heartbeat_timeout_ms)
        remaining_ms = (deadline - now) * 1000
        heartbeat_side = True
        wait_ms = remaining_ms
        if effective_timeout is not None and effective_timeout < remaining_ms:
            wait_ms = effective_timeout
            heartbeat_side = False
        socket.settimeout(ceil(wait_ms) / 1000)
        try:
            payload = socket.recv()
        except websocket.WebSocketTimeoutException:
            if heartbeat_side:
                self._raise_heartbeat_timeout(heartbeat_timeout_ms)
            return None
        except (websocket.WebSocketConnectionClosedException, OSError):
            self._connection_lost(f"Event connection closed by Bridge ({self.event_endpoint})")
        except websocket.WebSocketException as error:
            self._connection_lost(f"Event connection failed: {error} ({self.event_endpoint})")
        event = self._decode_event(payload)
        received_at = _monotonic()
        if received_at >= deadline:
            self._raise_heartbeat_timeout(heartbeat_timeout_ms)
        if event.type == common_pb2.EVENT_HEARTBEAT:
            self._heartbeat_deadline = received_at + heartbeat_timeout_ms / 1000
        return event

    def _decode_event(self, payload: Any) -> common_pb2.BridgeEvent:
        if isinstance(payload, str):
            raise BridgeProtocolError(
                f"Bridge returned a text frame; binary expected ({self.event_endpoint})"
            )
        try:
            return common_pb2.BridgeEvent.FromString(payload)
        except Exception as error:
            raise BridgeProtocolError(
                f"Bridge returned a malformed event ({self.event_endpoint})"
            ) from error

    def _connection_lost(self, message: str) -> NoReturn:
        if self._connection_lost_message is None:
            self._connection_lost_message = message
        raise BridgeConnectionLostError(message)

    def _raise_heartbeat_timeout(self, heartbeat_timeout_ms: int) -> NoReturn:
        self._connection_lost(
            "Connection lost because heartbeats are missing: "
            f"no heartbeat within {heartbeat_timeout_ms} ms ({self.event_endpoint})"
        )

    def __next__(self) -> common_pb2.BridgeEvent:
        while (event := self.receive()) is None:
            pass
        return event
