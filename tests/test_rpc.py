from __future__ import annotations

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

from .support import (
    FakeConnections,
    FakeWebSocket,
    RequestAwareBridgeSocket,
    response_scenario,
)


def install(
    monkeypatch: pytest.MonkeyPatch, *results: FakeWebSocket | Exception
) -> FakeConnections:
    connections = FakeConnections(*results)
    monkeypatch.setattr(rpc_module.websocket, "create_connection", connections)
    return connections


def test_default_endpoint_is_v3() -> None:
    assert DEFAULT_RPC_ENDPOINT == "ws://127.0.0.1:54000/bridge/v3/rpc"
    assert PROTOCOL_VERSION == 3


def test_custom_endpoint_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = RequestAwareBridgeSocket()
    connections = install(monkeypatch, socket)

    with BridgeRpcClient("ws://example.test/rpc") as client:
        client.get_timer_state()

    assert connections.endpoints == ["ws://example.test/rpc"]


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
    response_envelope = bridge_pb2.Response(protocol_version=3, session_id=42)
    response_type = type(response).__name__
    response_field = {
        "GetTimerStateResponse": "get_timer_state",
        "GetRunResponse": "get_run",
        "GetAttemptResponse": "get_attempt",
        "GetContextStateResponse": "get_context_state",
        "GetCompletedCountResponse": "get_completed_count",
    }[response_type]
    getattr(response_envelope, response_field).CopyFrom(response)
    socket = RequestAwareBridgeSocket(scenarios={method: response_envelope})
    connections = install(monkeypatch, socket)

    with BridgeRpcClient() as client:
        actual = getattr(client, method)()
        request = bridge_pb2.Request.FromString(socket.sent[0])

        assert request.protocol_version == 3
        assert request.WhichOneof("body") == method
        assert actual == expected
        assert client.session_id == 42

    assert connections.endpoints == [DEFAULT_RPC_ENDPOINT]


def test_timer_operation_returns_empty_v3_operation_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socket = RequestAwareBridgeSocket()
    install(monkeypatch, socket)

    with BridgeRpcClient() as client:
        response = client.start()

    request = bridge_pb2.Request.FromString(socket.sent[0])
    assert request.timer_operation.operation == common_pb2.TIMER_START
    assert not response.ListFields()


def test_game_time_operation_preserves_optional_ticks(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = RequestAwareBridgeSocket()
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
        bridge_pb2.Response(protocol_version=2, session_id=42),
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
    socket = RequestAwareBridgeSocket(
        scenarios={
            "timer_operation": response_scenario(
                error=common_pb2.BridgeError(
                    code=common_pb2.INVALID_ARGUMENT, message="invalid operation"
                )
            )
        }
    )
    install(monkeypatch, socket)

    with BridgeRpcClient() as client, pytest.raises(BridgeRemoteError) as error:
        client.start()
    assert error.value.code == common_pb2.INVALID_ARGUMENT
    assert error.value.message == "invalid operation"


def test_error_response_updates_session_before_raising_remote_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socket = RequestAwareBridgeSocket(
        scenarios={
            "timer_operation": response_scenario(
                session_id=99,
                error=common_pb2.BridgeError(
                    code=common_pb2.OPERATION_FAILED, message="restart response"
                ),
            )
        }
    )
    install(monkeypatch, socket)
    client = BridgeRpcClient()

    with pytest.raises(BridgeRemoteError) as error:
        client.start()

    assert error.value.code == common_pb2.OPERATION_FAILED
    assert error.value.message == "restart response"
    assert client.session_id == 99
    client.close()


@pytest.mark.parametrize(
    "response",
    [
        bridge_pb2.Response(protocol_version=3, session_id=0),
        bridge_pb2.Response(
            protocol_version=3,
            session_id=42,
            get_run=bridge_pb2.GetRunResponse(),
        ),
    ],
    ids=["zero-session", "unexpected-body"],
)
def test_invalid_session_or_response_body_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    response: bridge_pb2.Response,
) -> None:
    socket = RequestAwareBridgeSocket(scenarios={"get_timer_state": response})
    install(monkeypatch, socket)

    with BridgeRpcClient() as client, pytest.raises(BridgeProtocolError):
        client.get_timer_state()
    assert client.session_id == 0


def test_missing_response_body_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    install(
        monkeypatch,
        RequestAwareBridgeSocket(
            scenarios={
                "get_timer_state": [
                    response_scenario(get_timer_state=bridge_pb2.GetTimerStateResponse()),
                    response_scenario(session_id=99),
                ]
            }
        ),
    )

    with BridgeRpcClient() as client:
        client.get_timer_state()
        with pytest.raises(BridgeProtocolError):
            client.get_timer_state()
        assert client.session_id == 42


def test_text_and_malformed_responses_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for payload in ("text", b"\x08"):
        install(monkeypatch, FakeWebSocket([payload]))
        with BridgeRpcClient() as client, pytest.raises(BridgeProtocolError):
            client.get_timer_state()


@pytest.mark.parametrize(
    ("failed_socket", "error_type"),
    [
        (FakeWebSocket(timeout=True), BridgeResponseTimeoutError),
        (
            FakeWebSocket([websocket.WebSocketConnectionClosedException("closed")]),
            BridgeClientError,
        ),
        (FakeWebSocket([websocket.WebSocketException("transport error")]), BridgeClientError),
    ],
)
def test_transport_failure_does_not_retry_and_next_rpc_works(
    monkeypatch: pytest.MonkeyPatch,
    failed_socket: FakeWebSocket,
    error_type: type[Exception],
) -> None:
    replacement = RequestAwareBridgeSocket()
    install(monkeypatch, failed_socket, replacement)
    client = BridgeRpcClient()

    with pytest.raises(error_type):
        client.start()

    assert replacement.sent == []
    assert not client.start().ListFields()
    client.close()


def test_response_timeout_ms_is_applied_to_websocket(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = RequestAwareBridgeSocket()
    install(monkeypatch, socket)

    with BridgeRpcClient(response_timeout_ms=12) as client:
        client.get_timer_state()

    assert socket.recv_timeout == 0.012


def test_negative_response_timeout_is_rejected() -> None:
    with pytest.raises(ValueError, match="response_timeout_ms"):
        BridgeRpcClient(response_timeout_ms=-1)


def test_close_is_idempotent_and_rejects_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = FakeWebSocket()
    install(monkeypatch, socket)
    client = BridgeRpcClient()
    client.close()
    client.close()

    with pytest.raises(BridgeClientError):
        client.get_timer_state()


def test_connect_failure_is_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, websocket.WebSocketException("handshake failed"))

    with pytest.raises(BridgeClientError) as error:
        BridgeRpcClient()

    assert DEFAULT_RPC_ENDPOINT in str(error.value)
