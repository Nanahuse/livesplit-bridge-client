from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
import websocket

from livesplit_bridge import (
    DEFAULT_RPC_ENDPOINT,
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
        on_recv: Any = None,
    ) -> None:
        self.messages = list(messages)
        self.always_timeout = timeout
        self.on_recv = on_recv
        self.sent: list[bytes] = []
        self.recv_timeout: float | None = None
        self.closed = False

    def send_binary(self, payload: bytes) -> None:
        self.sent.append(payload)

    def recv(self) -> Any:
        if self.on_recv is not None:
            self.on_recv()
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


def encoded_response(request_id: int, **body: Any) -> bytes:
    return bridge_pb2.Response(
        protocol_version=2,
        request_id=request_id,
        **body,
    ).SerializeToString()


def install(
    monkeypatch: pytest.MonkeyPatch, *results: FakeWebSocket | Exception
) -> FakeConnections:
    connections = FakeConnections(*results)
    monkeypatch.setattr(rpc_module.websocket, "create_connection", connections)
    return connections


def test_get_timer_state_sends_binary_request_and_returns_timer_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = common_pb2.TimerState(
        session_id=42,
        state_revision=5,
        phase=common_pb2.RUNNING,
        split_index=3,
        run_revision=1,
        attempt_revision=2,
        runtime_revision=4,
    )
    socket = FakeWebSocket(
        [
            encoded_response(
                1,
                get_timer_state=bridge_pb2.GetTimerStateResponse(timer_state=expected),
            )
        ]
    )
    connections = install(monkeypatch, socket)

    with BridgeRpcClient() as client:
        actual = client.get_timer_state()

    request = bridge_pb2.Request.FromString(socket.sent[0])
    assert request.protocol_version == 2
    assert request.request_id == 1
    assert request.HasField("get_timer_state")
    assert actual == expected
    assert socket.closed
    assert connections.endpoints == [DEFAULT_RPC_ENDPOINT]
    assert DEFAULT_RPC_ENDPOINT.endswith("/bridge/v2/rpc")
    assert socket.recv_timeout == client.response_timeout_ms / 1000


def test_get_run_sends_binary_request_and_returns_run_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = run_pb2.RunState(
        session_id=42,
        run_revision=3,
        game_name="Super Mario World",
        category_name="11 Exit",
    )
    socket = FakeWebSocket(
        [
            encoded_response(
                1,
                get_run=bridge_pb2.GetRunResponse(run=expected),
            )
        ]
    )
    install(monkeypatch, socket)

    with BridgeRpcClient() as client:
        actual = client.get_run()

    request = bridge_pb2.Request.FromString(socket.sent[0])
    assert request.protocol_version == 2
    assert request.request_id == 1
    assert request.HasField("get_run")
    assert actual == expected


def test_get_attempt_returns_attempt_state(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = common_pb2.AttemptState(
        session_id=42,
        attempt_revision=2,
        attempt_count=5,
        completed_count=3,
    )
    socket = FakeWebSocket(
        [
            encoded_response(
                1,
                get_attempt=bridge_pb2.GetAttemptResponse(attempt=expected),
            )
        ]
    )
    install(monkeypatch, socket)

    with BridgeRpcClient() as client:
        actual = client.get_attempt()

    request = bridge_pb2.Request.FromString(socket.sent[0])
    assert request.HasField("get_attempt")
    assert actual == expected


def test_get_runtime_state_returns_runtime_state(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = common_pb2.RuntimeState(
        session_id=42,
        runtime_revision=2,
        current_timing_method=common_pb2.REAL_TIME,
        current_comparison="Personal Best",
        global_hotkeys_enabled=True,
    )
    socket = FakeWebSocket(
        [
            encoded_response(
                1,
                get_runtime_state=bridge_pb2.GetRuntimeStateResponse(runtime_state=expected),
            )
        ]
    )
    install(monkeypatch, socket)

    with BridgeRpcClient() as client:
        actual = client.get_runtime_state()

    request = bridge_pb2.Request.FromString(socket.sent[0])
    assert request.HasField("get_runtime_state")
    assert actual == expected


def test_attach_returns_v2_attach_response(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = bridge_pb2.AttachResponse(
        session_id=42,
        timer_state=common_pb2.TimerState(session_id=42, phase=common_pb2.NOT_RUNNING),
    )
    socket = FakeWebSocket([encoded_response(1, attach=expected)])
    install(monkeypatch, socket)

    with BridgeRpcClient() as client:
        actual = client.attach()

    request = bridge_pb2.Request.FromString(socket.sent[0])
    assert request.HasField("attach")
    assert actual == expected
    assert actual.timer_state.phase == common_pb2.NOT_RUNNING


def test_timer_operation_returns_operation_response_with_timer_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timer_state = common_pb2.TimerState(session_id=42, phase=common_pb2.RUNNING, split_index=1)
    socket = FakeWebSocket(
        [
            encoded_response(
                1,
                operation=common_pb2.OperationResponse(
                    success=True, message="OK", timer_state=timer_state
                ),
            )
        ]
    )
    install(monkeypatch, socket)
    client = BridgeRpcClient()

    result = client.start()

    request = bridge_pb2.Request.FromString(socket.sent[0])
    assert request.timer_operation.operation == common_pb2.TIMER_START
    assert result.success
    assert result.timer_state == timer_state
    client.close()


def test_game_time_operation_returns_operation_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timer_state = common_pb2.TimerState(session_id=42, is_game_time_initialized=True)
    socket = FakeWebSocket(
        [
            encoded_response(
                1,
                operation=common_pb2.OperationResponse(success=True, timer_state=timer_state),
            )
        ]
    )
    install(monkeypatch, socket)
    client = BridgeRpcClient()

    result = client.set_game_time_ticks(123_450_000)

    request = bridge_pb2.Request.FromString(socket.sent[0])
    assert request.game_time_operation.operation == common_pb2.SET
    assert request.game_time_operation.HasField("ticks")
    assert request.game_time_operation.ticks == 123_450_000
    assert result.timer_state == timer_state
    client.close()


def test_remote_error_exposes_code_and_message(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = FakeWebSocket(
        [
            encoded_response(
                1,
                error=common_pb2.BridgeError(code=7, message="not attached"),
            )
        ]
    )
    install(monkeypatch, socket)
    client = BridgeRpcClient()

    with pytest.raises(BridgeRemoteError, match="not attached") as error:
        client.attach()

    assert error.value.code == 7
    client.close()


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (encoded_response(99), "Request ID mismatch"),
        (
            bridge_pb2.Response(protocol_version=1, request_id=1).SerializeToString(),
            "Protocol version mismatch",
        ),
    ],
)
def test_protocol_mismatch_is_rejected(
    monkeypatch: pytest.MonkeyPatch, response: bytes, message: str
) -> None:
    install(monkeypatch, FakeWebSocket([response]))
    client = BridgeRpcClient()

    with pytest.raises(BridgeProtocolError, match=message):
        client.attach()

    client.close()


def test_text_frame_is_rejected_as_protocol_error(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeWebSocket(["not binary"]))
    client = BridgeRpcClient()

    with pytest.raises(BridgeProtocolError, match="text frame"):
        client.attach()

    client.close()


def test_malformed_protobuf_is_rejected_as_protocol_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(monkeypatch, FakeWebSocket([b"\x08"]))
    client = BridgeRpcClient()

    with pytest.raises(BridgeProtocolError, match="malformed"):
        client.attach()

    client.close()


def test_connection_closed_during_request_is_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = FakeWebSocket([websocket.WebSocketConnectionClosedException("closed")])
    install(monkeypatch, closed, FakeWebSocket())
    client = BridgeRpcClient()

    with pytest.raises(BridgeClientError, match="closed"):
        client.attach()

    assert closed.closed
    client.close()


def test_connection_reset_during_request_is_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset = FakeWebSocket([ConnectionResetError("reset by peer")])
    install(monkeypatch, reset, FakeWebSocket())
    client = BridgeRpcClient()

    with pytest.raises(BridgeClientError, match="closed"):
        client.attach()

    assert reset.closed
    client.close()


def test_timeout_recreates_connection_and_next_request_uses_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timed_out = FakeWebSocket(timeout=True)
    replacement = FakeWebSocket(
        [encoded_response(2, operation=common_pb2.OperationResponse(success=True))]
    )
    install(monkeypatch, timed_out, replacement)
    client = BridgeRpcClient(response_timeout_ms=12)

    with pytest.raises(BridgeResponseTimeoutError, match="12 ms"):
        client.attach()

    result = client.start()

    assert result.success
    assert timed_out.closed
    assert not replacement.closed
    request = bridge_pb2.Request.FromString(replacement.sent[0])
    assert request.request_id == 2
    client.close()
    assert replacement.closed


class TimeoutThenDelayedWebSocket(FakeWebSocket):
    def __init__(self, delayed: bytes) -> None:
        super().__init__()
        self.delayed = delayed
        self.recv_calls = 0

    def recv(self) -> Any:
        self.recv_calls += 1
        if self.recv_calls == 1:
            raise websocket.WebSocketTimeoutException("timed out")
        return self.delayed


def test_timeout_does_not_misidentify_delayed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = encoded_response(1, operation=common_pb2.OperationResponse(success=True))
    timed_out = TimeoutThenDelayedWebSocket(stale)
    replacement = FakeWebSocket(
        [encoded_response(2, operation=common_pb2.OperationResponse(success=True))]
    )
    install(monkeypatch, timed_out, replacement)
    client = BridgeRpcClient(response_timeout_ms=12)

    with pytest.raises(BridgeResponseTimeoutError):
        client.attach()

    assert client.start().success

    assert timed_out.closed
    assert timed_out.recv_calls == 1
    request = bridge_pb2.Request.FromString(replacement.sent[0])
    assert request.request_id == 2
    client.close()


def test_close_is_idempotent_and_closed_client_rejects_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socket = FakeWebSocket()
    install(monkeypatch, socket)
    client = BridgeRpcClient()
    client.close()
    client.close()

    with pytest.raises(BridgeClientError, match="closed"):
        client.attach()


@pytest.mark.parametrize(
    "failure",
    [
        OSError("connection refused"),
        websocket.WebSocketException("handshake failed"),
    ],
)
def test_connect_failure_is_wrapped_as_client_error(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    install(monkeypatch, failure)

    with pytest.raises(BridgeClientError, match="rpc") as error:
        BridgeRpcClient()

    assert DEFAULT_RPC_ENDPOINT in str(error.value)
