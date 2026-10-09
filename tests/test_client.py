from __future__ import annotations

from typing import cast

import pytest
import websocket

from livesplit_bridge import (
    DEFAULT_EVENT_ENDPOINT,
    DEFAULT_RPC_ENDPOINT,
    BridgeClient,
    BridgeClientError,
    BridgeRemoteError,
    BridgeResyncRequiredError,
    BridgeSyncState,
    bridge_pb2,
    common_pb2,
    run_pb2,
)
from livesplit_bridge import events as events_module
from livesplit_bridge import rpc as rpc_module

from .test_rpc import FakeConnections, FakeWebSocket, encoded_response


def synchronization_responses(session_id: int = 42, *, start_request_id: int = 1) -> list[bytes]:
    return [
        encoded_response(
            start_request_id,
            session_id=session_id,
            get_timer_state=bridge_pb2.GetTimerStateResponse(
                timer_state=common_pb2.TimerState(phase=common_pb2.NOT_RUNNING)
            ),
        ),
        encoded_response(
            start_request_id + 1,
            session_id=session_id,
            get_attempt=bridge_pb2.GetAttemptResponse(
                attempt=common_pb2.AttemptState(attempt_count=4)
            ),
        ),
        encoded_response(
            start_request_id + 2,
            session_id=session_id,
            get_run=bridge_pb2.GetRunResponse(run=run_pb2.RunState(game_name="Game")),
        ),
        encoded_response(
            start_request_id + 3,
            session_id=session_id,
            get_context_state=bridge_pb2.GetContextStateResponse(
                context_state=common_pb2.ContextState(current_comparison="Personal Best")
            ),
        ),
    ]


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


def test_reconnect_synchronizes_before_replacing_both_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous_event = common_pb2.BridgeEvent(
        session_id=42, event_sequence=45, type=common_pb2.EVENT_RUN_CHANGED
    )
    next_event = common_pb2.BridgeEvent(
        session_id=42, event_sequence=900, type=common_pb2.EVENT_RUN_CHANGED
    )
    old_events = FakeWebSocket([previous_event.SerializeToString()])
    old_rpc = FakeWebSocket()
    new_events = FakeWebSocket([next_event.SerializeToString()])
    new_rpc = FakeWebSocket(synchronization_responses())
    connections = install(monkeypatch, old_events, old_rpc, new_events, new_rpc)
    client = BridgeClient()

    assert client.receive() == previous_event
    state = client.reconnect()
    assert isinstance(state, BridgeSyncState)
    assert state.session_id == 42
    assert state.attempt.attempt_count == 4

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
    assert len(new_rpc.sent) == 4
    assert client.receive() == next_event
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


def test_reconnect_keeps_old_connections_if_synchronize_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_events = FakeWebSocket()
    old_rpc = FakeWebSocket()
    new_events = FakeWebSocket()
    inconsistent = synchronization_responses()
    inconsistent[2] = encoded_response(
        3,
        session_id=77,
        get_run=bridge_pb2.GetRunResponse(run=run_pb2.RunState()),
    )
    new_rpc = FakeWebSocket(inconsistent)
    install(monkeypatch, old_events, old_rpc, new_events, new_rpc)
    client = BridgeClient()

    with pytest.raises(BridgeResyncRequiredError, match="changed during synchronize"):
        client.reconnect()

    assert not old_events.closed
    assert not old_rpc.closed
    assert new_events.closed
    assert new_rpc.closed
    client.close()


def test_synchronize_returns_consistent_snapshot_and_optional_completed_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_socket = FakeWebSocket()
    responses = synchronization_responses()
    responses.append(
        encoded_response(
            5,
            get_completed_count=bridge_pb2.GetCompletedCountResponse(
                completed_count=common_pb2.CompletedCount(completed_count=9)
            ),
        )
    )
    rpc_socket = FakeWebSocket(responses)
    install(monkeypatch, event_socket, rpc_socket)
    client = BridgeClient()

    state = client.synchronize(include_completed_count=True)

    assert state.session_id == 42
    assert state.timer_state.phase == common_pb2.NOT_RUNNING
    assert state.attempt.attempt_count == 4
    assert state.run.game_name == "Game"
    assert state.context_state.current_comparison == "Personal Best"
    assert state.completed_count is not None
    assert state.completed_count.completed_count == 9
    assert len(rpc_socket.sent) == 5
    client.close()


def test_synchronize_does_not_return_partial_state_on_session_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_socket = FakeWebSocket()
    responses = synchronization_responses()
    responses[2] = encoded_response(
        3,
        session_id=77,
        get_run=bridge_pb2.GetRunResponse(run=run_pb2.RunState()),
    )
    install(monkeypatch, event_socket, FakeWebSocket(responses))
    client = BridgeClient()

    with pytest.raises(BridgeResyncRequiredError, match="changed during synchronize"):
        client.synchronize()

    client.close()


def test_synchronize_error_response_on_new_session_requires_resync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc_socket = FakeWebSocket(
        [
            *synchronization_responses()[:2],
            encoded_response(
                3,
                session_id=77,
                error=common_pb2.BridgeError(
                    code=common_pb2.OPERATION_FAILED,
                    message="runtime changed",
                ),
            ),
        ]
    )
    install(monkeypatch, FakeWebSocket(), rpc_socket)
    client = BridgeClient()

    with pytest.raises(BridgeResyncRequiredError, match="changed during synchronize"):
        client.synchronize()

    client.close()


def test_synchronize_resets_event_sequence_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        common_pb2.BridgeEvent(session_id=42, event_sequence=n, type=common_pb2.EVENT_RUN_CHANGED)
        for n in (100, 500)
    ]
    event_socket = FakeWebSocket([event.SerializeToString() for event in events])
    install(monkeypatch, event_socket, FakeWebSocket(synchronization_responses()))
    client = BridgeClient()

    assert client.receive() == events[0]
    client.synchronize()
    assert client.receive() == events[1]
    client.close()


def test_first_event_can_establish_temporary_session_before_rpc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = common_pb2.BridgeEvent(
        session_id=42,
        event_sequence=57,
        type=common_pb2.EVENT_RUN_CHANGED,
    )
    event_socket = FakeWebSocket([event.SerializeToString()])
    rpc_socket = FakeWebSocket(
        [encoded_response(1, get_timer_state=bridge_pb2.GetTimerStateResponse())]
    )
    install(monkeypatch, event_socket, rpc_socket)
    client = BridgeClient()

    assert client.receive() == event
    assert client.get_timer_state() == common_pb2.TimerState()
    client.close()


def test_rpc_session_change_requires_resync_before_more_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc_socket = FakeWebSocket(
        [
            encoded_response(1, session_id=42, get_timer_state=bridge_pb2.GetTimerStateResponse()),
            encoded_response(2, session_id=99, get_timer_state=bridge_pb2.GetTimerStateResponse()),
            *synchronization_responses(99, start_request_id=3),
            encoded_response(7, session_id=99, get_timer_state=bridge_pb2.GetTimerStateResponse()),
        ]
    )
    install(monkeypatch, FakeWebSocket(), rpc_socket)
    client = BridgeClient()

    client.get_timer_state()
    with pytest.raises(BridgeResyncRequiredError, match="changed from 42 to 99"):
        client.get_timer_state()
    with pytest.raises(BridgeResyncRequiredError, match="Full synchronize"):
        client.get_timer_state()

    assert client.synchronize().session_id == 99
    assert client.get_timer_state() == common_pb2.TimerState()
    client.close()


def test_rpc_event_session_mismatch_requires_resync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = common_pb2.BridgeEvent(
        session_id=77, event_sequence=1, type=common_pb2.EVENT_RUN_CHANGED
    )
    rpc_socket = FakeWebSocket(
        [encoded_response(1, session_id=42, get_timer_state=bridge_pb2.GetTimerStateResponse())]
    )
    install(monkeypatch, FakeWebSocket([event.SerializeToString()]), rpc_socket)
    client = BridgeClient()

    client.get_timer_state()
    with pytest.raises(BridgeResyncRequiredError, match="does not match RPC session"):
        client.receive()
    client.close()


def test_event_sequence_gap_session_mismatch_and_unknown_type_require_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = [
        (
            [
                common_pb2.BridgeEvent(
                    session_id=42, event_sequence=10, type=common_pb2.EVENT_RUN_CHANGED
                ),
                common_pb2.BridgeEvent(
                    session_id=42, event_sequence=12, type=common_pb2.EVENT_RUN_CHANGED
                ),
            ],
            "sequence gap",
        ),
        (
            [
                common_pb2.BridgeEvent(
                    session_id=42, event_sequence=10, type=common_pb2.EVENT_RUN_CHANGED
                ),
                common_pb2.BridgeEvent(
                    session_id=77, event_sequence=11, type=common_pb2.EVENT_RUN_CHANGED
                ),
            ],
            "session",
        ),
        (
            [
                common_pb2.BridgeEvent(
                    session_id=42,
                    event_sequence=10,
                    type=cast(common_pb2.BridgeEventType, 999),
                )
            ],
            "Unknown Bridge event",
        ),
    ]
    for events, error_text in cases:
        event_socket = FakeWebSocket([event.SerializeToString() for event in events])
        install(monkeypatch, event_socket, FakeWebSocket())
        client = BridgeClient()
        if len(events) > 1:
            client.receive()
        with pytest.raises(BridgeResyncRequiredError, match=error_text):
            client.receive()
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
