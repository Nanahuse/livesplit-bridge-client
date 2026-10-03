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


def _snapshot_response(request_id: int, snapshot: common_pb2.TimerSnapshot) -> bytes:
    return encoded_response(
        request_id,
        get_snapshot=bridge_pb2.GetSnapshotResponse(snapshot=snapshot),
    )


def test_subscriber_is_created_before_rpc_client(monkeypatch: pytest.MonkeyPatch) -> None:
    sub_socket = FakeWebSocket()
    req_socket = FakeWebSocket()
    connections = install(monkeypatch, sub_socket, req_socket)

    client = BridgeClient()

    assert connections.endpoints == [DEFAULT_EVENT_ENDPOINT, DEFAULT_RPC_ENDPOINT]
    assert client.rpc.rpc_endpoint == DEFAULT_RPC_ENDPOINT
    assert client.events.event_endpoint == DEFAULT_EVENT_ENDPOINT
    client.close()


def test_rpc_operations_delegate_to_client(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = common_pb2.TimerSnapshot(session_id=42, split_index=3)
    sub_socket = FakeWebSocket()
    req_socket = FakeWebSocket(
        [
            _snapshot_response(1, expected),
            encoded_response(2, operation=common_pb2.OperationResponse(success=True)),
        ]
    )
    install(monkeypatch, sub_socket, req_socket)
    client = BridgeClient()

    assert client.snapshot() == expected
    assert client.start().success

    request = bridge_pb2.Request.FromString(req_socket.sent[1])
    assert request.timer_operation.operation == common_pb2.TIMER_START
    client.close()


def test_get_run_delegates_to_rpc_client(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = run_pb2.RunSnapshot(session_id=42, run_revision=3, game_name="Super Mario World")
    sub_socket = FakeWebSocket()
    req_socket = FakeWebSocket(
        [
            encoded_response(1, get_run=bridge_pb2.GetRunResponse(run=expected)),
        ]
    )
    install(monkeypatch, sub_socket, req_socket)
    client = BridgeClient()

    assert client.get_run() == expected

    request = bridge_pb2.Request.FromString(req_socket.sent[0])
    assert request.HasField("get_run")
    client.close()


def test_receive_and_iteration_use_current_subscriber(monkeypatch: pytest.MonkeyPatch) -> None:
    first = common_pb2.BridgeEvent(
        session_id=9, event_sequence=1, type=common_pb2.EVENT_STATE_SNAPSHOT
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


class SnapshotTrackingWebSocket(FakeWebSocket):
    def __init__(self, calls: list[Any], messages: Any = ()) -> None:
        super().__init__(messages)
        self.calls = calls

    def send_binary(self, payload: bytes) -> None:
        self.calls.append("snapshot")
        super().send_binary(payload)


def test_reconnect_creates_subscriber_and_rpc_before_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    expected = common_pb2.TimerSnapshot(session_id=7, split_index=1)
    old_sub = FakeWebSocket()
    old_req = FakeWebSocket()
    new_req = SnapshotTrackingWebSocket(calls, [_snapshot_response(1, expected)])
    event = common_pb2.BridgeEvent(
        session_id=7, event_sequence=5, type=common_pb2.EVENT_TIMER_SPLIT
    )
    new_sub = FakeWebSocket([event.SerializeToString()])
    connections = TrackingConnections(calls, old_sub, old_req, new_sub, new_req)
    monkeypatch.setattr(websocket, "create_connection", connections)

    client = BridgeClient()
    result = client.reconnect()

    assert result == expected
    assert calls == [
        ("connect", DEFAULT_EVENT_ENDPOINT),
        ("connect", DEFAULT_RPC_ENDPOINT),
        ("connect", DEFAULT_EVENT_ENDPOINT),
        ("connect", DEFAULT_RPC_ENDPOINT),
        "snapshot",
    ]
    assert old_sub.closed
    assert old_req.closed
    assert not new_sub.closed
    assert client.receive() == event
    client.close()


def test_reconnect_keeps_old_resources_when_snapshot_fails_and_retry_succeeds(
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
    retry_sub = FakeWebSocket()
    retry_req = FakeWebSocket([_snapshot_response(1, common_pb2.TimerSnapshot(session_id=7))])
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


def test_reconnect_reuses_stored_endpoint_and_response_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_sub = FakeWebSocket()
    old_req = FakeWebSocket()
    new_sub = FakeWebSocket()
    new_req = FakeWebSocket([_snapshot_response(1, common_pb2.TimerSnapshot(session_id=7))])
    connections = install(monkeypatch, old_sub, old_req, new_sub, new_req)

    client = BridgeClient(
        "ws://custom:1234",
        "ws://custom-events:1235",
        response_timeout_ms=42,
    )

    client.reconnect()

    assert connections.endpoints == [
        "ws://custom-events:1235",
        "ws://custom:1234",
        "ws://custom-events:1235",
        "ws://custom:1234",
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
    snapshot = common_pb2.TimerSnapshot(session_id=7, event_sequence=3)
    new_req = FakeWebSocket([_snapshot_response(1, snapshot)])
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
    assert client.reconnect() == snapshot
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
        client.snapshot()

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
    new_req = FakeWebSocket([_snapshot_response(1, common_pb2.TimerSnapshot(session_id=7))])
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
    new_req = FakeWebSocket([_snapshot_response(1, common_pb2.TimerSnapshot(session_id=7))])
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
