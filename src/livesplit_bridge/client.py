from __future__ import annotations

from typing import Any, Self

import zmq

from .protocol import bridge_pb2, common_pb2

DEFAULT_RPC_ENDPOINT = "tcp://127.0.0.1:54000"
PROTOCOL_VERSION = 1


class BridgeClientError(RuntimeError):
    """Base class for client and remote protocol failures."""


class BridgeTimeoutError(BridgeClientError):
    """Raised when one RPC or event receive operation exceeds its timeout."""


class BridgeEventStreamLostError(BridgeClientError):
    """Raised when the event stream is no longer trustworthy because heartbeats are missing."""


class BridgeProtocolError(BridgeClientError):
    """Raised when the Bridge returns a response that violates the protocol."""


class BridgeRemoteError(BridgeClientError):
    """Raised when the Bridge returns a structured error."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"Bridge error {code}: {message}")


class BridgeClient:
    """Synchronous ZeroMQ REQ/REP client for LiveSplit.Bridge.

    This class is single-threaded: a client owns one ZeroMQ socket and must only be used
    from a single thread at a time.
    """

    def __init__(
        self,
        rpc_endpoint: str = DEFAULT_RPC_ENDPOINT,
        *,
        timeout_ms: int = 3000,
        context: Any | None = None,
    ) -> None:
        if timeout_ms < 0:
            raise ValueError("timeout_ms must be non-negative")
        self.rpc_endpoint = rpc_endpoint
        self.timeout_ms = timeout_ms
        self._context = context if context is not None else zmq.Context()
        self._owns_context = context is None
        self._socket: Any | None = None
        self._next_request_id = 1
        self._closed = False
        try:
            self._connect()
        except Exception:
            if self._owns_context:
                self._context.term()
            raise

    def _connect(self) -> None:
        socket = self._context.socket(zmq.REQ)
        try:
            socket.setsockopt(zmq.LINGER, 0)
            socket.connect(self.rpc_endpoint)
        except Exception:
            socket.close()
            raise
        self._socket = socket

    def _reset_socket(self) -> None:
        if self._socket is not None:
            self._socket.close()
        self._connect()

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
            raise BridgeClientError("Client is closed")
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def request(self, request: bridge_pb2.Request) -> bridge_pb2.Response:
        if self._closed or self._socket is None:
            raise BridgeClientError("Client is closed")
        if not isinstance(request, bridge_pb2.Request):
            raise TypeError("request must be a bridge_pb2.Request")

        request_id = self._next_request_id
        self._next_request_id += 1
        request.protocol_version = PROTOCOL_VERSION
        request.request_id = request_id

        self._socket.send(request.SerializeToString())
        if not self._socket.poll(self.timeout_ms, zmq.POLLIN):
            self._reset_socket()
            raise BridgeTimeoutError(
                f"RPC timed out after {self.timeout_ms} ms ({self.rpc_endpoint})"
            )

        response = bridge_pb2.Response.FromString(self._socket.recv())
        if response.protocol_version != PROTOCOL_VERSION:
            raise BridgeProtocolError(
                f"Protocol version mismatch: expected {PROTOCOL_VERSION}, "
                f"got {response.protocol_version}"
            )
        if response.request_id != request_id:
            raise BridgeProtocolError(
                f"Request ID mismatch: expected {request_id}, got {response.request_id}"
            )
        if response.HasField("error"):
            raise BridgeRemoteError(response.error.code, response.error.message)
        return response

    def attach(self) -> bridge_pb2.AttachResponse:
        response = self.request(bridge_pb2.Request(attach=bridge_pb2.AttachRequest()))
        return response.attach

    def snapshot(self) -> common_pb2.TimerSnapshot:
        response = self.request(bridge_pb2.Request(get_snapshot=bridge_pb2.GetSnapshotRequest()))
        return response.get_snapshot.snapshot

    def timer_operation(
        self, operation: common_pb2.TimerOperationType
    ) -> common_pb2.OperationResponse:
        response = self.request(
            bridge_pb2.Request(
                timer_operation=bridge_pb2.TimerOperationRequest(operation=operation)
            )
        )
        return response.operation

    def game_time_operation(
        self, operation: common_pb2.GameTimeOperationType, *, ticks: int | None = None
    ) -> common_pb2.OperationResponse:
        operation_request = bridge_pb2.GameTimeOperationRequest(operation=operation)
        if ticks is not None:
            operation_request.ticks = ticks
        response = self.request(bridge_pb2.Request(game_time_operation=operation_request))
        return response.operation

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
