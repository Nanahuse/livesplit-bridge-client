from __future__ import annotations

from typing import Any, Self

import websocket
from pydantic import TypeAdapter

from ._api import BridgeApi
from ._json import decode_object
from .models import (
    UINT32_MAX,
    AttemptState,
    CompletedCount,
    ContextState,
    ErrorResponse,
    GameTimeRequest,
    QueryMethod,
    QueryRequest,
    RpcRequest,
    RpcResult,
    RunIcons,
    RunState,
    SuccessResponse,
    TimerRequest,
    TimerState,
)

DEFAULT_RPC_ENDPOINT = "ws://127.0.0.1:54000/bridge/v4/rpc"

_REQUEST = TypeAdapter(RpcRequest)
_RESPONSE = TypeAdapter(SuccessResponse[RpcResult] | ErrorResponse)
_QUERY_RESULTS = {
    QueryMethod.GET_TIMER_STATE: TimerState,
    QueryMethod.GET_RUN: RunState,
    QueryMethod.GET_RUN_ICONS: RunIcons,
    QueryMethod.GET_ATTEMPT: AttemptState,
    QueryMethod.GET_CONTEXT_STATE: ContextState,
    QueryMethod.GET_COMPLETED_COUNT: CompletedCount,
}


class BridgeClientError(RuntimeError):
    """Base class for client and remote protocol failures."""


class BridgeResponseTimeoutError(BridgeClientError):
    """Raised when a Bridge response exceeds its deadline."""


class BridgeProtocolError(BridgeClientError):
    """Raised when the Bridge returns a response that violates the protocol."""


class BridgeResyncRequiredError(BridgeClientError):
    """Raised when cached client state may be stale and needs a full synchronize()."""


class BridgeReconnectRequiredError(BridgeResyncRequiredError):
    """Raised when RPC and Events may belong to different runtime sessions."""


class BridgeRemoteError(BridgeClientError):
    """Raised when the Bridge returns a structured error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"Bridge error {code}: {message}")


class BridgeRpcClient(BridgeApi):
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
        self.session_change: tuple[int, int] | None = None
        self.transport_reset = False
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

    def _discard_socket(self) -> None:
        socket = self._socket
        self._socket = None
        if socket is not None:
            try:
                shutdown = getattr(socket, "shutdown", None)
                if shutdown is not None:
                    shutdown()
                else:
                    socket.close()
            except Exception:
                pass

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

    def request(self, request: RpcRequest) -> SuccessResponse[RpcResult]:
        self.session_change = None
        self.transport_reset = False
        if self._closed or self._socket is None:
            raise BridgeClientError("Client is closed")
        if not isinstance(request, (QueryRequest, TimerRequest, GameTimeRequest)):
            raise TypeError("request must be a typed v4 RPC request")

        request_id = self._next_request_id
        # Revalidate caller-owned models too: Pydantic models can be mutated after creation.
        request = _REQUEST.validate_python(request.model_dump()).model_copy(
            update={"request_id": request_id}
        )
        self._next_request_id = (request_id + 1) & UINT32_MAX

        socket = self._socket
        try:
            socket.settimeout(self._timeout_seconds())
            socket.send(request.model_dump_json(), opcode=websocket.ABNF.OPCODE_TEXT)
            opcode, payload = socket.recv_data()
        except websocket.WebSocketTimeoutException as error:
            self.transport_reset = True
            self._discard_socket()
            raise BridgeResponseTimeoutError(
                f"No Bridge response within {self.response_timeout_ms} ms ({self.rpc_endpoint})"
            ) from error
        except (websocket.WebSocketConnectionClosedException, OSError) as error:
            self.transport_reset = True
            self._discard_socket()
            raise BridgeClientError(
                f"RPC connection closed by Bridge ({self.rpc_endpoint})"
            ) from error
        except websocket.WebSocketException as error:
            self.transport_reset = True
            self._discard_socket()
            raise BridgeClientError(f"RPC failed: {error} ({self.rpc_endpoint})") from error

        if opcode == websocket.ABNF.OPCODE_CLOSE:
            self.transport_reset = True
            self._discard_socket()
            raise BridgeClientError(f"RPC connection closed by Bridge ({self.rpc_endpoint})")

        try:
            if opcode == websocket.ABNF.OPCODE_BINARY:
                raise BridgeProtocolError(
                    f"Bridge returned a binary frame; text expected ({self.rpc_endpoint})"
                )
            if opcode != websocket.ABNF.OPCODE_TEXT:
                raise BridgeProtocolError(
                    f"Bridge returned an unsupported WebSocket frame ({self.rpc_endpoint})"
                )
            response = _RESPONSE.validate_python(decode_object(payload))
            if response.request_id != request_id:
                raise BridgeProtocolError(
                    f"Request ID mismatch: expected {request_id}, got {response.request_id}"
                )
            if isinstance(response, SuccessResponse):
                expected_type = (
                    _QUERY_RESULTS[request.method]
                    if isinstance(request, QueryRequest)
                    else type(None)
                )
                if not isinstance(response.result, expected_type):
                    raise BridgeProtocolError(
                        f"Response result mismatch for {request.method}: "
                        f"expected {expected_type.__name__}, got {type(response.result).__name__}"
                    )
        except BridgeProtocolError:
            self.transport_reset = True
            self._discard_socket()
            raise
        except Exception as error:
            self.transport_reset = True
            self._discard_socket()
            raise BridgeProtocolError(
                f"Bridge returned a malformed response ({self.rpc_endpoint})"
            ) from error

        if isinstance(response, ErrorResponse):
            self._commit_session(response.session_id)
            raise BridgeRemoteError(response.error.code, response.error.message)
        self._commit_session(response.session_id)
        return response

    def _commit_session(self, new_session_id: int) -> None:
        previous_session_id = self.session_id
        committed_session_id = int(new_session_id)
        self.session_change = (
            (previous_session_id, committed_session_id)
            if previous_session_id not in (0, committed_session_id)
            else None
        )
        self.session_id = committed_session_id
