from __future__ import annotations

from typing import Any

import pytest
import websocket

from livesplit_bridge import (
    DEFAULT_EVENT_ENDPOINT,
    DEFAULT_RPC_ENDPOINT,
    BridgeClient,
    BridgeClientError,
    BridgeConnectionLostError,
    BridgeRemoteError,
    bridge_pb2,
    common_pb2,
    run_pb2,
)
from livesplit_bridge import events as events_module

from .test_rpc import FakeConnections, FakeWebSocket, encoded_response


def install(
    monkeypatch: pytest.MonkeyPatch, *results: FakeWebSocket | Exception
) -> FakeConnections:
    connections = FakeConnections(*results)
    monkeypatch.setattr(websocket, "create_connection", connections)
    return connections


def _attach_response(request_id: int, attached: bridge_pb2.AttachResponse) -> bytes:
    return encoded_response(request_id, attach=attached)


def test_subscriber_is_created_before_rpc_client(monkeypatch: pytest.MonkeyPatch) -> None:
    sub_socket = FakeWebSocket()
    req_socket = FakeWebSocket()
    connections = install(monkeypatch, sub_socket, req_socket)

    client = BridgeClient()

    assert connections.endpoints == [DEFAULT_EVENT_ENDPOINT, DEFAULT_RPC_ENDPOINT]
    assert client.rpc.rpc_endpoint == DEFAULT_RPC_ENDPOINT
    assert client.events.event_endpoint == DEFAULT_EVENT_ENDPOINT
    assert DEFAULT_RPC_ENDPOINT == "ws://127.0.0.1:54000/bridge/v2/rpc"
    assert DEFAULT_EVENT_ENDPOINT == "ws://127.0.0.1:54000/bridge/v2/events"
    client.close()


def test_rpc_operations_delegate_to_client(monkeypatch: pytest.MonkeyPatch) -> None:
    attached = bridge_pb2.AttachResponse(
        session_id=42,
        timer_state=common_pb2.TimerState(session_id=42, phase=common_pb2.NOT_RUNNING),
    )
    timer_state = common_pb2.TimerState(session_id=42, split_index=3, phase=common_pb2.RUNNING)
    run_state = run_pb2.RunState(session_id=42, run_revision=1, game_name="Super Mario World")
    attempt = common_pb2.AttemptState(
        session_id=42, attempt_revision=2, attempt_count=5, completed_count=3
    )
    runtime = common_pb2.RuntimeState(
        session_id=42, runtime_revision=1, current_comparison="Personal Best"
    )

    sub_socket = FakeWebSocket()
    req_socket = FakeWebSocket(
        [
            _attach_response(1, attached),
            encoded_response(
                2, get_timer_state=bridge_pb2.GetTimerStateResponse(timer_state=timer_state)
            ),
            encoded_response(3, get_run=bridge_pb2.GetRunResponse(run=run_state)),
            encoded_response(4, get_attempt=bridge_pb2.GetAttemptResponse(attempt=attempt)),
            encoded_response(
                5,
                get_runtime_state=bridge_pb2.GetRuntimeStateResponse(runtime_state=runtime),
            ),
            encoded_response(
                6,
                operation=common_pb2.OperationResponse(success=True, timer_state=timer_state),
            ),
        ]
    )
    install(monkeypatch, sub_socket, req_socket)
    client = BridgeClient()

    assert client.attach() == attached
    assert client.get_timer_state() == timer_state
    assert client.get_run() == run_state
    assert client.get_attempt() == attempt
    assert client.get_runtime_state() == runtime
    assert client.start().success

    request = bridge_pb2.Request.FromString(req_socket.sent[5])
    assert request.timer_operation.operation == common_pb2.TIMER_START
    client.close()


def test_receive_and_iteration_use_current_subscriber(monkeypatch: pytest.MonkeyPatch) -> None:
    first = common_pb2.BridgeEvent(
        session_id=9, event_sequence=1, type=common_pb2.EVENT_TIMER_STARTED
    )
    second = common_pb2.BridgeEvent(
        session_id=9, event_sequence=2, type=common_pb2.EVENT_TIMER_SPLIT
    )
    sub_socket = FakeWebSocket([first.SerializeToString(), second.SerializeToString()])
    install(monkeypatch, sub_socket, FakeWebSocket())
    client = BridgeClient()

    assert client.receive() == first
    assert iter(client) is client
    assert next(client) == second
    client.close()


def test_receive_timeout_is_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    sub_socket = FakeWebSocket(timeout=True)
    install(monkeypatch, sub_socket, FakeWebSocket())
    client = BridgeClient()

    assert client.receive(timeout_ms=7) is None

    client.close()


class TrackingConnections(FakeConnections):
    def __init__(self, calls: list[Any], *results: FakeWebSocket | Exception) -> None:
        super().__init__(*results)
        self.calls = calls

    def __call__(self, endpoint: str, **kwargs: Any) -> FakeWebSocket:
        self.calls.append(("connect", endpoint))
        return super().__call__(endpoint, **kwargs)


class AttachTrackingWebSocket(FakeWebSocket):
    def __init__(self, calls: list[Any], messages: Any = ()) -> None:
        super().__init__(messages)
        self.calls = calls

    def send_binary(self, payload: bytes) -> None:
        self.calls.append("attach")
        super().send_binary(payload)


def test_reconnect_creates_subscriber_and_rpc_before_attach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    attached = bridge_pb2.AttachResponse(
        session_id=7,
        timer_state=common_pb2.TimerState(session_id=7, phase=common_pb2.RUNNING),
    )
    old_sub = FakeWebSocket()
    old_req = FakeWebSocket()
    new_req = AttachTrackingWebSocket(calls, [_attach_response(1, attached)])
    event = common_pb2.BridgeEvent(
        session_id=7,
        event_sequence=5,
        type=common_pb2.EVENT_TIMER_SPLIT,
        timer_state=common_pb2.TimerState(session_id=7, phase=common_pb2.RUNNING),
    )
    new_sub = FakeWebSocket([event.SerializeToString()])
    connections = TrackingConnections(calls, old_sub, old_req, new_sub, new_req)
    monkeypatch.setattr(websocket, "create_connection", connections)

    client = BridgeClient()
    result = client.reconnect()

    assert result == attached
    assert calls == [
        ("connect", DEFAULT_EVENT_ENDPOINT),
        ("connect", DEFAULT_RPC_ENDPOINT),
        ("connect", DEFAULT_EVENT_ENDPOINT),
        ("connect", DEFAULT_RPC_ENDPOINT),
        "attach",
    ]
    assert old_sub.closed
    assert old_req.closed
    assert not new_sub.closed
    assert client.receive() == event
    client.close()


def test_reconnect_keeps_old_resources_when_attach_fails_and_retry_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_sub = FakeWebSocket()
    old_req = FakeWebSocket()
    new_sub = FakeWebSocket()
    new_req = FakeWebSocket(
        [
            encoded_response(
                1,
                error=common_pb2.BridgeError(code=7, message="not attached"),
            ),
        ]
    )
    attached = bridge_pb2.AttachResponse(session_id=7)
    retry_sub = FakeWebSocket()
    retry_req = FakeWebSocket([_attach_response(1, attached)])
    install(monkeypatch, old_sub, old_req, new_sub, new_req, retry_sub, retry_req)

    client = BridgeClient()

    with pytest.raises(BridgeRemoteError, match="not attached"):
        client.reconnect()

    assert not old_sub.closed
    assert not old_req.closed
    assert new_sub.closed
    assert new_req.closed
    assert client.events is not None

    result = client.reconnect()

    assert old_sub.closed
    assert old_req.closed
    assert not retry_sub.closed
    assert not retry_req.closed
    assert result.session_id == 7
    client.close()


def test_reconnect_keeps_old_resources_when_new_events_connection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_sub = FakeWebSocket()
    old_req = FakeWebSocket()
    install(monkeypatch, old_sub, old_req, websocket.WebSocketException("event connect boom"))
    client = BridgeClient()

    with pytest.raises(BridgeClientError, match="event"):
        client.reconnect()

    assert not old_sub.closed
    assert not old_req.closed
    assert client.events is not None
    client.close()


def test_reconnect_closes_new_events_when_new_rpc_connection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_sub = FakeWebSocket()
    old_req = FakeWebSocket()
    new_sub = FakeWebSocket()
    install(
        monkeypatch, old_sub, old_req, new_sub, websocket.WebSocketException("rpc connect boom")
    )
    client = BridgeClient()

    with pytest.raises(BridgeClientError, match="rpc"):
        client.reconnect()

    assert not old_sub.closed
    assert not old_req.closed
    assert new_sub.closed
    client.close()


def test_reconnect_reuses_stored_endpoint_and_response_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_sub = FakeWebSocket()
    old_req = FakeWebSocket()
    new_sub = FakeWebSocket()
    new_req = FakeWebSocket([_attach_response(1, bridge_pb2.AttachResponse(session_id=7))])
    connections = install(monkeypatch, old_sub, old_req, new_sub, new_req)

    client = BridgeClient(
        "ws://custom:1234/bridge/v2/rpc",
        "ws://custom-events:1235/bridge/v2/events",
        response_timeout_ms=42,
    )

    client.reconnect()

    assert connections.endpoints == [
        "ws://custom-events:1235/bridge/v2/events",
        "ws://custom:1234/bridge/v2/rpc",
        "ws://custom-events:1235/bridge/v2/events",
        "ws://custom:1234/bridge/v2/rpc",
    ]
    assert client.rpc.response_timeout_ms == 42
    client.close()


class FakeMonotonic:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_reconnect_recovers_from_event_stream_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    old_sub = FakeWebSocket()
    old_req = FakeWebSocket()
    attached = bridge_pb2.AttachResponse(
        session_id=7,
        timer_state=common_pb2.TimerState(session_id=7, state_revision=3),
    )
    new_req = FakeWebSocket([_attach_response(1, attached)])
    heartbeat = common_pb2.BridgeEvent(
        session_id=7,
        event_sequence=3,
        type=common_pb2.EVENT_HEARTBEAT,
    )
    new_sub = FakeWebSocket([heartbeat.SerializeToString()])
    install(monkeypatch, old_sub, old_req, new_sub, new_req)
    client = BridgeClient(heartbeat_timeout_ms=100)

    clock.now = 0.15
    with pytest.raises(BridgeConnectionLostError):
        client.receive()

    clock.now = 0.18
    assert client.reconnect() == attached
    assert client.receive() == heartbeat
    client.close()


def test_close_is_idempotent_and_rejects_operations_and_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sub_socket = FakeWebSocket()
    req_socket = FakeWebSocket()
    install(monkeypatch, sub_socket, req_socket)
    client = BridgeClient()
    client.close()
    client.close()

    assert sub_socket.closed
    assert req_socket.closed

    with pytest.raises(BridgeClientError, match="closed"):
        client.get_timer_state()

    with pytest.raises(BridgeClientError, match="closed"):
        _ = client.rpc

    with pytest.raises(BridgeClientError, match="closed"):
        _ = client.events

    with pytest.raises(BridgeClientError, match="closed"):
        next(client)


class CloseFailingWebSocket(FakeWebSocket):
    def close(self) -> None:
        super().close()
        raise RuntimeError("close boom")


def test_close_cleans_remaining_resources_after_subscriber_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sub_socket = CloseFailingWebSocket()
    req_socket = FakeWebSocket()
    install(monkeypatch, sub_socket, req_socket)
    client = BridgeClient()

    with pytest.raises(RuntimeError, match="close boom"):
        client.close()

    assert sub_socket.closed
    assert req_socket.closed
    client.close()


def test_reconnect_keeps_new_resources_when_old_events_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_sub = CloseFailingWebSocket()
    old_req = FakeWebSocket()
    new_sub = FakeWebSocket()
    new_req = FakeWebSocket([_attach_response(1, bridge_pb2.AttachResponse(session_id=7))])
    install(monkeypatch, old_sub, old_req, new_sub, new_req)
    client = BridgeClient()
    old_subscriber = client.events

    with pytest.raises(RuntimeError, match="close boom"):
        client.reconnect()

    assert client.events is not old_subscriber
    assert not new_sub.closed
    assert not new_req.closed
    assert old_req.closed
    client.close()


def test_reconnect_keeps_new_resources_when_old_rpc_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_sub = FakeWebSocket()
    old_req = CloseFailingWebSocket()
    new_sub = FakeWebSocket()
    new_req = FakeWebSocket([_attach_response(1, bridge_pb2.AttachResponse(session_id=7))])
    install(monkeypatch, old_sub, old_req, new_sub, new_req)
    client = BridgeClient()

    with pytest.raises(RuntimeError, match="close boom"):
        client.reconnect()

    assert old_sub.closed
    assert not new_sub.closed
    assert not new_req.closed
    client.close()


def test_partial_initialization_failure_closes_created_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sub_socket = FakeWebSocket()
    install(monkeypatch, sub_socket)

    with pytest.raises(IndexError):
        BridgeClient()

    assert sub_socket.closed


def test_connect_failure_closes_subscriber_and_is_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sub_socket = FakeWebSocket()
    install(monkeypatch, sub_socket, websocket.WebSocketException("connect boom"))

    with pytest.raises(BridgeClientError, match="rpc") as error:
        BridgeClient()

    assert sub_socket.closed
    assert DEFAULT_RPC_ENDPOINT in str(error.value)
