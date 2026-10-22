from __future__ import annotations

import json
from typing import Any

import pytest
import websocket
from pydantic import ValidationError

from livesplit_bridge import (
    DEFAULT_RPC_ENDPOINT,
    AttemptState,
    BridgeClientError,
    BridgeProtocolError,
    BridgeRemoteError,
    BridgeResponseTimeoutError,
    BridgeRpcClient,
    CompletedCount,
    ContextState,
    GameTimeOperation,
    QueryMethod,
    QueryRequest,
    RunIcons,
    RunState,
    TimerState,
)
from livesplit_bridge import rpc as rpc_module

from .support import FakeConnections, FakeWebSocket, RequestAwareBridgeSocket, query_result


def install(
    monkeypatch: pytest.MonkeyPatch, *sockets: FakeWebSocket | Exception
) -> FakeConnections:
    connections = FakeConnections(*sockets)
    monkeypatch.setattr(rpc_module.websocket, "create_connection", connections)
    return connections


def test_default_endpoint_and_custom_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    assert DEFAULT_RPC_ENDPOINT == "ws://127.0.0.1:54000/bridge/v4/rpc"
    connections = install(monkeypatch, RequestAwareBridgeSocket())
    with BridgeRpcClient("ws://example.test/rpc") as client:
        client.get_timer_state()
    assert connections.endpoints == ["ws://example.test/rpc"]


@pytest.mark.parametrize(
    ("method", "model"),
    [
        ("get_timer_state", TimerState),
        ("get_run", RunState),
        ("get_run_icons", RunIcons),
        ("get_attempt", AttemptState),
        ("get_context_state", ContextState),
        ("get_completed_count", CompletedCount),
    ],
)
def test_queries_use_json_text_and_return_models(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    model: type[Any],
) -> None:
    socket = RequestAwareBridgeSocket()
    install(monkeypatch, socket)
    with BridgeRpcClient() as client:
        actual = getattr(client, method)()
        assert isinstance(actual, model)
        assert actual == model.model_validate(query_result(method))
        assert client.session_id == 42
    assert json.loads(socket.sent[0]) == {"request_id": 1, "method": method}


@pytest.mark.parametrize(
    ("method", "args", "wire_method", "params"),
    [
        *[
            (name, (), "timer_operation", {"operation": name})
            for name in ("start", "split", "skip", "undo", "reset", "pause", "resume")
        ],
        ("initialize_game_time", (), "game_time_operation", {"operation": "initialize"}),
        (
            "set_game_time_ticks",
            (-(2**63),),
            "game_time_operation",
            {"operation": "set", "ticks": -(2**63)},
        ),
        ("pause_game_time", (), "game_time_operation", {"operation": "pause"}),
        ("resume_game_time", (), "game_time_operation", {"operation": "resume"}),
    ],
)
def test_controls_return_none(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    args: tuple[Any, ...],
    wire_method: str,
    params: dict[str, Any],
) -> None:
    socket = RequestAwareBridgeSocket()
    install(monkeypatch, socket)
    with BridgeRpcClient() as client:
        assert getattr(client, method)(*args) is None
    assert json.loads(socket.sent[0]) == {"request_id": 1, "method": wire_method, "params": params}


def test_ids_wrap_through_zero_and_do_not_mutate_request(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = RequestAwareBridgeSocket()
    install(monkeypatch, socket)
    request = QueryRequest(request_id=123, method=QueryMethod.GET_RUN)
    with BridgeRpcClient() as client:
        client._next_request_id = 2**32 - 1
        for _ in range(3):
            client.request(request)
    assert [json.loads(message)["request_id"] for message in socket.sent] == [2**32 - 1, 0, 1]
    assert request.request_id == 123


@pytest.mark.parametrize(
    "payload",
    [
        b"binary",
        "not JSON",
        "[]",
        "null",
        '{"request_id":1,"request_id":1}',
        '{"request_id":1,"session_id":42,"result":NaN}',
        '{"request_id":1,"session_id":42,"result":Infinity}',
        (websocket.ABNF.OPCODE_TEXT, b"\xff"),
        (websocket.ABNF.OPCODE_PONG, b""),
        json.dumps({"request_id": 2, "session_id": 42, "result": query_result("get_timer_state")}),
        *[
            json.dumps(envelope)
            for envelope in (
                {"request_id": 1, "session_id": 0, "result": None},
                {"request_id": 1, "session_id": 2**32, "result": None},
                {"request_id": True, "session_id": 42, "result": None},
                {"request_id": 1, "session_id": "42", "result": None},
                {"request_id": 1, "session_id": 42, "result": query_result("get_run")},
                {"request_id": 1, "session_id": 42, "result": None},
                {"request_id": 1, "session_id": 42, "result": {}},
                {"request_id": 1, "session_id": 42},
                {"request_id": 1, "session_id": 42, "result": None, "error": None},
                {"request_id": 1, "session_id": 42, "error": {"code": 3, "message": "bad"}},
                {"request_id": 1, "session_id": 42, "error": {"code": "unknown", "message": "bad"}},
                {"request_id": 1, "session_id": 42, "result": None, "protocol_version": 4},
            )
        ],
    ],
)
def test_invalid_responses_discard_connection(
    monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    socket = FakeWebSocket([payload])
    connections = install(monkeypatch, socket)
    with BridgeRpcClient() as client:
        with pytest.raises(BridgeProtocolError):
            client.get_timer_state()
        assert client.session_id == 0
        assert client.transport_reset
        assert socket.shutdown_called
        with pytest.raises(BridgeClientError):
            client.get_timer_state()
    assert len(connections.endpoints) == 1


def test_text_frame_utf8_bytes_are_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    body = json.dumps({"request_id": 1, "session_id": 42, "result": query_result("get_run")})
    install(monkeypatch, FakeWebSocket([(websocket.ABNF.OPCODE_TEXT, body.encode())]))
    with BridgeRpcClient() as client:
        assert client.get_run().game_name == "Game"


def test_control_rejects_query_result(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = RequestAwareBridgeSocket(
        scenarios={
            "timer_operation": {
                "session_id": 42,
                "result": query_result("get_timer_state"),
            }
        }
    )
    install(monkeypatch, socket)
    with BridgeRpcClient() as client, pytest.raises(BridgeProtocolError):
        client.start()


@pytest.mark.parametrize(
    "code",
    [
        "invalid_request",
        "invalid_argument",
        "operation_failed",
        "internal_error",
        "permission_denied",
    ],
)
def test_remote_errors_keep_connection_and_commit_session(
    monkeypatch: pytest.MonkeyPatch,
    code: str,
) -> None:
    socket = RequestAwareBridgeSocket(
        scenarios={
            "timer_operation": {
                "session_id": 99,
                "error": {"code": code, "message": "操作失敗"},
            }
        }
    )
    install(monkeypatch, socket)
    with BridgeRpcClient() as client:
        client.get_timer_state()
        with pytest.raises(BridgeRemoteError) as error:
            client.start()
        assert error.value.code == code
        assert error.value.message == "操作失敗"
        assert client.session_id == 99
        assert client.session_change == (42, 99)
        assert not client.transport_reset
        client.get_timer_state()


@pytest.mark.parametrize(
    ("failed_socket", "error_type"),
    [
        (FakeWebSocket(timeout=True), BridgeResponseTimeoutError),
        (FakeWebSocket([(websocket.ABNF.OPCODE_CLOSE, b"")]), BridgeClientError),
        (
            FakeWebSocket([websocket.WebSocketConnectionClosedException("closed")]),
            BridgeClientError,
        ),
        (FakeWebSocket([websocket.WebSocketException("transport error")]), BridgeClientError),
        (FakeWebSocket([ConnectionResetError("reset")]), BridgeClientError),
    ],
)
def test_transport_failure_never_retries(
    monkeypatch: pytest.MonkeyPatch, failed_socket: FakeWebSocket, error_type: type[Exception]
) -> None:
    connections = install(monkeypatch, failed_socket)
    with BridgeRpcClient() as client:
        with pytest.raises(error_type):
            client.start()
        assert failed_socket.shutdown_called
        assert len(failed_socket.sent) == 1
        with pytest.raises(BridgeClientError):
            client.start()
        assert len(failed_socket.sent) == 1
    assert len(connections.endpoints) == 1


def test_timeout_and_close(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = RequestAwareBridgeSocket()
    install(monkeypatch, socket)
    client = BridgeRpcClient(response_timeout_ms=12)
    client.get_timer_state()
    assert socket.recv_timeout == 0.012
    client.close()
    client.close()
    assert socket.close_called
    with pytest.raises(BridgeClientError):
        client.get_timer_state()
    with pytest.raises(BridgeClientError):
        client.__enter__()


def test_bad_local_arguments_do_not_send(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = RequestAwareBridgeSocket()
    install(monkeypatch, socket)
    with BridgeRpcClient() as client:
        for ticks in (True, "1", 1.0, 2**63, -(2**63) - 1):
            with pytest.raises(ValidationError):
                client.set_game_time_ticks(ticks)  # ty: ignore[invalid-argument-type]
        with pytest.raises(ValueError):
            client.game_time_operation(GameTimeOperation.SET)
        with pytest.raises(ValueError):
            client.game_time_operation(GameTimeOperation.PAUSE, ticks=1)
        request = QueryRequest(request_id=0, method=QueryMethod.GET_RUN)
        request.request_id = -1
        with pytest.raises(ValidationError):
            client.request(request)
    assert not socket.sent


def test_negative_timeout_and_connect_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="response_timeout_ms"):
        BridgeRpcClient(response_timeout_ms=-1)
    install(monkeypatch, websocket.WebSocketException("handshake failed"))
    with pytest.raises(BridgeClientError, match=DEFAULT_RPC_ENDPOINT):
        BridgeRpcClient()
