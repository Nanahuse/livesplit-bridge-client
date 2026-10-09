from __future__ import annotations

from typing import Any, Self

import websocket

from .protocol import bridge_pb2, common_pb2, run_pb2

DEFAULT_RPC_ENDPOINT = "ws://127.0.0.1:54000/bridge/v3/rpc"
PROTOCOL_VERSION = 3


class BridgeClientError(RuntimeError):
    """Base class for client and remote protocol failures."""


class BridgeResponseTimeoutError(BridgeClientError):
    """Raised when a Bridge response exceeds its deadline."""


class BridgeProtocolError(BridgeClientError):
    """Raised when the Bridge returns a response that violates the protocol."""


class BridgeRemoteError(BridgeClientError):
    """Raised when the Bridge returns a structured error."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"Bridge error {code}: {message}")


class BridgeRpcClient:
    """Synchronous WebSocket client for LiveSplit.Bridge RPC.

    This class is single-threaded: a client owns one WebSocket connection and must only
    be used from a single thread at a time.
    """

    def __init__(
        self,
        rpc_endpoint: str = DEFAULT_RPC_ENDPOINT,
        *,
        response_timeout_ms: int = 3000,
    ) -> None:
        if response_timeout_ms < 0:
            raise ValueError("response_timeout_ms must be non-negative")
        self.rpc_endpoint = rpc_endpoint
        self.response_timeout_ms = response_timeout_ms
        self._socket: Any | None = None
        self._next_request_id = 1
        self.session_id: int = 0
        self._closed = False
        self._connect()

    def _timeout_seconds(self) -> float:
        return self.response_timeout_ms / 1000

    def _connect(self) -> None:
        try:
            socket = websocket.create_connection(
                self.rpc_endpoint,
                timeout=self._timeout_seconds(),
            )
        except (OSError, websocket.WebSocketException) as error:
            raise BridgeClientError(
                f"Failed to connect to RPC endpoint {self.rpc_endpoint}: {error}"
            ) from error
        self._socket = socket

    def _reset_socket(self) -> None:
        socket = self._socket
        self._socket = None
        if socket is not None:
            try:
                socket.close()
            except Exception:
                pass
        try:
            self._connect()
        except BridgeClientError:
            self._socket = None

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

        socket = self._socket
        socket.settimeout(self._timeout_seconds())
        try:
            socket.send_binary(request.SerializeToString())
            payload = socket.recv()
        except websocket.WebSocketTimeoutException as error:
            self._reset_socket()
            raise BridgeResponseTimeoutError(
                f"No Bridge response within {self.response_timeout_ms} ms ({self.rpc_endpoint})"
            ) from error
        except (websocket.WebSocketConnectionClosedException, OSError) as error:
            self._reset_socket()
            raise BridgeClientError(
                f"RPC connection closed by Bridge ({self.rpc_endpoint})"
            ) from error
        except websocket.WebSocketException as error:
            self._reset_socket()
            raise BridgeClientError(f"RPC failed: {error} ({self.rpc_endpoint})") from error

        if isinstance(payload, str):
            raise BridgeProtocolError(
                f"Bridge returned a text frame; binary expected ({self.rpc_endpoint})"
            )

        try:
            response = bridge_pb2.Response.FromString(payload)
        except Exception as error:
            raise BridgeProtocolError(
                f"Bridge returned a malformed response ({self.rpc_endpoint})"
            ) from error

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
        self.session_id = int(response.session_id)
        return response

    def get_timer_state(self) -> common_pb2.TimerState:
        response = self.request(
            bridge_pb2.Request(get_timer_state=bridge_pb2.GetTimerStateRequest())
        )
        return response.get_timer_state.timer_state

    def get_run(self) -> run_pb2.RunState:
        response = self.request(bridge_pb2.Request(get_run=bridge_pb2.GetRunRequest()))
        return response.get_run.run

    def get_attempt(self) -> common_pb2.AttemptState:
        response = self.request(bridge_pb2.Request(get_attempt=bridge_pb2.GetAttemptRequest()))
        return response.get_attempt.attempt

    def get_context_state(self) -> common_pb2.ContextState:
        response = self.request(
            bridge_pb2.Request(get_context_state=bridge_pb2.GetContextStateRequest())
        )
        return response.get_context_state.context_state

    def get_completed_count(self) -> common_pb2.CompletedCount:
        response = self.request(
            bridge_pb2.Request(get_completed_count=bridge_pb2.GetCompletedCountRequest())
        )
        return response.get_completed_count.completed_count

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
