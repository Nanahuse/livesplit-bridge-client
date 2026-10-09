from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
import websocket

from livesplit_bridge import (
    DEFAULT_RPC_ENDPOINT,
    PROTOCOL_VERSION,
    BridgeClientError,
    BridgeProtocolError,
    BridgeRemoteError,
    BridgeResponseTimeoutError,
    BridgeRpcClient,
    bridge_pb2,
    common_pb2,
    run_pb2,
)
from livesplit_bridge import rpc as rpc_module


class FakeWebSocket:
    def __init__(
        self,
        messages: Iterable[Any] = (),
        *,
        timeout: bool = False,
    ) -> None:
        self.messages = list(messages)
        self.always_timeout = timeout
        self.sent: list[bytes] = []
        self.recv_timeout: float | None = None
        self.closed = False

    def send_binary(self, payload: bytes) -> None:
        self.sent.append(payload)

    def recv(self) -> Any:
        if self.messages:
            item = self.messages.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        if self.always_timeout:
            raise websocket.WebSocketTimeoutException("timed out")
        raise websocket.WebSocketConnectionClosedException("closed")

    def settimeout(self, value: float | None) -> None:
        self.recv_timeout = value

    def close(self) -> None:
        self.closed = True


class FakeConnections:
    def __init__(self, *results: FakeWebSocket | Exception) -> None:
        self.results = list(results)
        self.endpoints: list[str] = []

    def __call__(self, endpoint: str, **kwargs: Any) -> FakeWebSocket:
        self.endpoints.append(endpoint)
        if not self.results:
            raise IndexError("no more fake websockets")
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def encoded_response(request_id: int, *, session_id: int = 42, **body: Any) -> bytes:
    return bridge_pb2.Response(
        protocol_version=3,
        request_id=request_id,
        session_id=session_id,
        **body,
    ).SerializeToString()


def install(
    monkeypatch: pytest.MonkeyPatch, *results: FakeWebSocket | Exception
) -> FakeConnections:
    connections = FakeConnections(*results)
    monkeypatch.setattr(rpc_module.websocket, "create_connection", connections)
    return connections


def test_default_endpoint_is_v3() -> None:
    assert DEFAULT_RPC_ENDPOINT == "ws://127.0.0.1:54000/bridge/v3/rpc"
    assert PROTOCOL_VERSION == 3


@pytest.mark.parametrize(
    ("method", "response", "expected"),
    [
        (
            "get_timer_state",
            bridge_pb2.GetTimerStateResponse(
                timer_state=common_pb2.TimerState(phase=common_pb2.RUNNING, split_index=3)
            ),
            common_pb2.TimerState(phase=common_pb2.RUNNING, split_index=3),
        ),
        (
            "get_run",
            bridge_pb2.GetRunResponse(
                run=run_pb2.RunState(game_name="Super Mario World", category_name="11 Exit")
            ),
            run_pb2.RunState(game_name="Super Mario World", category_name="11 Exit"),
        ),
        (
            "get_attempt",
            bridge_pb2.GetAttemptResponse(attempt=common_pb2.AttemptState(attempt_count=5)),
            common_pb2.AttemptState(attempt_count=5),
        ),
        (
            "get_context_state",
            bridge_pb2.GetContextStateResponse(
                context_state=common_pb2.ContextState(
                    current_timing_method=common_pb2.GAME_TIME,
                    current_comparison="Personal Best",
                )
            ),
            common_pb2.ContextState(
                current_timing_method=common_pb2.GAME_TIME,
                current_comparison="Personal Best",
            ),
        ),
        (
            "get_completed_count",
            bridge_pb2.GetCompletedCountResponse(
                completed_count=common_pb2.CompletedCount(completed_count=3)
            ),
            common_pb2.CompletedCount(completed_count=3),
        ),
    ],
)
def test_query_methods_send_v3_binary_requests_and_return_payload(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    response: bridge_pb2.GetTimerStateResponse
    | bridge_pb2.GetRunResponse
    | bridge_pb2.GetAttemptResponse
    | bridge_pb2.GetContextStateResponse
    | bridge_pb2.GetCompletedCountResponse,
    expected: Any,
) -> None:
    response_envelope = bridge_pb2.Response(protocol_version=3, request_id=1, session_id=42)
    response_type = type(response).__name__
    response_field = {
        "GetTimerStateResponse": "get_timer_state",
        "GetRunResponse": "get_run",
        "GetAttemptResponse": "get_attempt",
        "GetContextStateResponse": "get_context_state",
        "GetCompletedCountResponse": "get_completed_count",
    }[response_type]
    getattr(response_envelope, response_field).CopyFrom(response)
    socket = FakeWebSocket([response_envelope.SerializeToString()])
    connections = install(monkeypatch, socket)

    with BridgeRpcClient() as client:
        actual = getattr(client, method)()
        request = bridge_pb2.Request.FromString(socket.sent[0])

        assert request.protocol_version == 3
        assert request.request_id == 1
        assert request.WhichOneof("body") == method
        assert actual == expected
        assert client.session_id == 42
        assert socket.recv_timeout == client.response_timeout_ms / 1000

    assert socket.closed
    assert connections.endpoints == [DEFAULT_RPC_ENDPOINT]


def test_timer_operation_returns_empty_v3_operation_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socket = FakeWebSocket([encoded_response(1, operation=common_pb2.OperationResponse())])
    install(monkeypatch, socket)

    with BridgeRpcClient() as client:
        response = client.start()

    request = bridge_pb2.Request.FromString(socket.sent[0])
    assert request.timer_operation.operation == common_pb2.TIMER_START
    assert not response.ListFields()


def test_game_time_operation_preserves_optional_ticks(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = FakeWebSocket([encoded_response(1, operation=common_pb2.OperationResponse())])
    install(monkeypatch, socket)

    with BridgeRpcClient() as client:
        client.set_game_time_ticks(1234)

    request = bridge_pb2.Request.FromString(socket.sent[0])
    assert request.game_time_operation.operation == common_pb2.SET
    assert request.game_time_operation.HasField("ticks")
    assert request.game_time_operation.ticks == 1234


@pytest.mark.parametrize(
    "response",
    [
        bridge_pb2.Response(protocol_version=2, request_id=1, session_id=42),
        bridge_pb2.Response(protocol_version=3, request_id=2, session_id=42),
    ],
    ids=["protocol-version", "request-id"],
)
def test_invalid_response_envelope_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    response: bridge_pb2.Response,
) -> None:
    install(monkeypatch, FakeWebSocket([response.SerializeToString()]))

    with BridgeRpcClient() as client, pytest.raises(BridgeProtocolError):
        client.get_timer_state()


def test_remote_error_is_exposed(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = FakeWebSocket(
        [
            encoded_response(
                1,
                error=common_pb2.BridgeError(
                    code=common_pb2.INVALID_ARGUMENT,
                    message="invalid operation",
                ),
            )
        ]
    )
    install(monkeypatch, socket)

    with BridgeRpcClient() as client, pytest.raises(BridgeRemoteError, match="invalid operation"):
        client.start()


def test_text_and_malformed_responses_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for payload, expected in [("text", "text frame"), (b"\x08", "malformed")]:
        install(monkeypatch, FakeWebSocket([payload]))
        with BridgeRpcClient() as client, pytest.raises(BridgeProtocolError, match=expected):
            client.get_timer_state()


def test_timeout_reconnects_and_next_request_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timed_out = FakeWebSocket(timeout=True)
    replacement = FakeWebSocket([encoded_response(2, operation=common_pb2.OperationResponse())])
    install(monkeypatch, timed_out, replacement)
    client = BridgeRpcClient(response_timeout_ms=12)

    with pytest.raises(BridgeResponseTimeoutError, match="12 ms"):
        client.start()

    assert not client.start().ListFields()
    assert timed_out.closed
    client.close()
    assert replacement.closed


def test_connection_close_is_wrapped_and_socket_is_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = FakeWebSocket([websocket.WebSocketConnectionClosedException("closed")])
    replacement = FakeWebSocket()
    install(monkeypatch, closed, replacement)
    client = BridgeRpcClient()

    with pytest.raises(BridgeClientError, match="closed"):
        client.get_timer_state()

    assert closed.closed
    client.close()


def test_close_is_idempotent_and_rejects_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = FakeWebSocket()
    install(monkeypatch, socket)
    client = BridgeRpcClient()
    client.close()
    client.close()

    with pytest.raises(BridgeClientError, match="closed"):
        client.get_timer_state()


def test_connect_failure_is_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, websocket.WebSocketException("handshake failed"))

    with pytest.raises(BridgeClientError, match="rpc") as error:
        BridgeRpcClient()

    assert DEFAULT_RPC_ENDPOINT in str(error.value)
