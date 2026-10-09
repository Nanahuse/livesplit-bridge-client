from __future__ import annotations

import pytest
import websocket

from livesplit_bridge import (
    DEFAULT_EVENT_ENDPOINT,
    DEFAULT_RPC_ENDPOINT,
    BridgeClient,
    BridgeClientError,
    BridgeRemoteError,
    bridge_pb2,
    common_pb2,
    run_pb2,
)
from livesplit_bridge import events as events_module
from livesplit_bridge import rpc as rpc_module

from .test_rpc import FakeConnections, FakeWebSocket, encoded_response


def install(
    monkeypatch: pytest.MonkeyPatch, *results: FakeWebSocket | Exception
) -> FakeConnections:
    connections = FakeConnections(*results)
    monkeypatch.setattr(events_module.websocket, "create_connection", connections)
    monkeypatch.setattr(rpc_module.websocket, "create_connection", connections)
    return connections


def test_subscriber_is_created_before_rpc_client(monkeypatch: pytest.MonkeyPatch) -> None:
    event_socket = FakeWebSocket()
    rpc_socket = FakeWebSocket()
    connections = install(monkeypatch, event_socket, rpc_socket)

    client = BridgeClient()

    assert connections.endpoints == [DEFAULT_EVENT_ENDPOINT, DEFAULT_RPC_ENDPOINT]
    assert client.rpc.rpc_endpoint == DEFAULT_RPC_ENDPOINT
    assert client.events.event_endpoint == DEFAULT_EVENT_ENDPOINT
    assert DEFAULT_RPC_ENDPOINT.endswith("/bridge/v3/rpc")
    assert DEFAULT_EVENT_ENDPOINT.endswith("/bridge/v3/events")
    client.close()


def test_query_and_operation_methods_delegate_to_v3_rpc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timer_state = common_pb2.TimerState(phase=common_pb2.RUNNING, split_index=3)
    run_state = run_pb2.RunState(game_name="Super Mario World")
    attempt = common_pb2.AttemptState(attempt_count=5)
    context = common_pb2.ContextState(current_comparison="Personal Best")
    completed = common_pb2.CompletedCount(completed_count=3)
    event_socket = FakeWebSocket()
    rpc_socket = FakeWebSocket(
        [
            encoded_response(
                1,
                get_timer_state=bridge_pb2.GetTimerStateResponse(timer_state=timer_state),
            ),
            encoded_response(2, get_run=bridge_pb2.GetRunResponse(run=run_state)),
            encoded_response(3, get_attempt=bridge_pb2.GetAttemptResponse(attempt=attempt)),
            encoded_response(
                4,
                get_context_state=bridge_pb2.GetContextStateResponse(context_state=context),
            ),
            encoded_response(
                5,
                get_completed_count=bridge_pb2.GetCompletedCountResponse(completed_count=completed),
            ),
            encoded_response(6, operation=common_pb2.OperationResponse()),
        ]
    )
    install(monkeypatch, event_socket, rpc_socket)
    client = BridgeClient()

    assert client.get_timer_state() == timer_state
    assert client.session_id == 42
    assert client.get_run() == run_state
    assert client.get_attempt() == attempt
    assert client.get_context_state() == context
    assert client.get_completed_count() == completed
    assert not client.start().ListFields()

    request = bridge_pb2.Request.FromString(rpc_socket.sent[5])
    assert request.protocol_version == 3
    assert request.timer_operation.operation == common_pb2.TIMER_START
    client.close()


def test_receive_and_iteration_use_v3_events(monkeypatch: pytest.MonkeyPatch) -> None:
    first = common_pb2.BridgeEvent(
        session_id=9,
        event_sequence=1,
        type=common_pb2.EVENT_TIMER_STARTED,
        timer_state=common_pb2.TimerState(phase=common_pb2.RUNNING),
    )
    second = common_pb2.BridgeEvent(
        session_id=9,
        event_sequence=2,
        type=common_pb2.EVENT_CONTEXT_CHANGED,
    )
    event_socket = FakeWebSocket([first.SerializeToString(), second.SerializeToString()])
    install(monkeypatch, event_socket, FakeWebSocket())
    client = BridgeClient()

    assert client.receive() == first
    assert iter(client) is client
    assert next(client) == second
    client.close()


def test_reconnect_replaces_both_connections_without_snapshot_rpc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_events = FakeWebSocket()
    old_rpc = FakeWebSocket()
    new_events = FakeWebSocket()
    new_rpc = FakeWebSocket()
    connections = install(monkeypatch, old_events, old_rpc, new_events, new_rpc)
    client = BridgeClient()

    assert client.reconnect() is None

    assert connections.endpoints == [
        DEFAULT_EVENT_ENDPOINT,
        DEFAULT_RPC_ENDPOINT,
        DEFAULT_EVENT_ENDPOINT,
        DEFAULT_RPC_ENDPOINT,
    ]
    assert old_events.closed
    assert old_rpc.closed
    assert not new_events.closed
    assert not new_rpc.closed
    assert new_rpc.sent == []
    client.close()


def test_reconnect_keeps_old_connections_if_new_rpc_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_events = FakeWebSocket()
    old_rpc = FakeWebSocket()
    new_events = FakeWebSocket()
    install(
        monkeypatch,
        old_events,
        old_rpc,
        new_events,
        websocket.WebSocketException("rpc connect failed"),
    )
    client = BridgeClient()

    with pytest.raises(BridgeClientError, match="rpc"):
        client.reconnect()

    assert not old_events.closed
    assert not old_rpc.closed
    assert new_events.closed
    client.close()


def test_initialization_failure_closes_event_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_socket = FakeWebSocket()
    install(monkeypatch, event_socket, websocket.WebSocketException("rpc failed"))

    with pytest.raises(BridgeClientError, match="rpc"):
        BridgeClient()

    assert event_socket.closed


def test_remote_rpc_error_is_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    event_socket = FakeWebSocket()
    rpc_socket = FakeWebSocket(
        [
            encoded_response(
                1,
                error=common_pb2.BridgeError(
                    code=common_pb2.OPERATION_FAILED,
                    message="operation failed",
                ),
            )
        ]
    )
    install(monkeypatch, event_socket, rpc_socket)
    client = BridgeClient()

    with pytest.raises(BridgeRemoteError, match="operation failed"):
        client.reset()

    client.close()


def test_close_is_idempotent_and_rejects_operations_and_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_socket = FakeWebSocket()
    rpc_socket = FakeWebSocket()
    install(monkeypatch, event_socket, rpc_socket)
    client = BridgeClient()
    client.close()
    client.close()

    assert event_socket.closed
    assert rpc_socket.closed
    with pytest.raises(BridgeClientError, match="closed"):
        client.get_timer_state()
    with pytest.raises(BridgeClientError, match="closed"):
        _ = client.rpc
    with pytest.raises(BridgeClientError, match="closed"):
        _ = client.events
    with pytest.raises(BridgeClientError, match="closed"):
        _ = client.session_id
