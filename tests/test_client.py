from __future__ import annotations

from typing import cast

import pytest
import websocket

from livesplit_bridge import (
    BridgeClient,
    BridgeClientError,
    BridgeConnectionLostError,
    BridgeProtocolError,
    BridgeReconnectRequiredError,
    BridgeRecoveryState,
    BridgeRemoteError,
    BridgeResponseTimeoutError,
    BridgeResyncRequiredError,
    bridge_pb2,
    common_pb2,
    run_pb2,
)
from livesplit_bridge import events as events_module
from livesplit_bridge import rpc as rpc_module

from .test_rpc import FakeConnections, FakeWebSocket, encoded_response


class CloseFailingWebSocket(FakeWebSocket):
    def close(self) -> None:
        super().close()
        raise RuntimeError("close failed")


class BridgeRespondingWebSocket(FakeWebSocket):
    def __init__(self, session_id: int = 42, completed_count: int = 9) -> None:
        super().__init__()
        self.session_id = session_id
        self.completed_count = completed_count

    def send_binary(self, payload: bytes) -> None:
        super().send_binary(payload)
        request = bridge_pb2.Request.FromString(payload)
        request_body = request.WhichOneof("body")
        response = bridge_pb2.Response(
            protocol_version=3,
            request_id=request.request_id,
            session_id=self.session_id,
        )
        response_fields = {
            "get_timer_state": bridge_pb2.GetTimerStateResponse(
                timer_state=common_pb2.TimerState(phase=common_pb2.NOT_RUNNING)
            ),
            "get_attempt": bridge_pb2.GetAttemptResponse(
                attempt=common_pb2.AttemptState(attempt_count=4)
            ),
            "get_run": bridge_pb2.GetRunResponse(run=run_pb2.RunState(game_name="Game")),
            "get_context_state": bridge_pb2.GetContextStateResponse(
                context_state=common_pb2.ContextState(current_comparison="Personal Best")
            ),
            "get_completed_count": bridge_pb2.GetCompletedCountResponse(
                completed_count=common_pb2.CompletedCount(completed_count=self.completed_count)
            ),
        }
        if request_body in response_fields:
            getattr(response, request_body).CopyFrom(response_fields[request_body])
        elif request_body in ("timer_operation", "game_time_operation"):
            response.operation.SetInParent()
        else:
            raise AssertionError(f"Unexpected Bridge request: {request_body}")
        self.messages.append(response.SerializeToString())


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


def test_event_received_during_initial_sync_remains_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_event = common_pb2.BridgeEvent(
        session_id=42,
        event_sequence=74,
        type=common_pb2.EVENT_RUN_CHANGED,
    )
    install(
        monkeypatch,
        FakeWebSocket([initial_event.SerializeToString()]),
        BridgeRespondingWebSocket(),
    )
    client = BridgeClient()

    state = client.synchronize()
    assert state.session_id == 42
    assert client.receive() == initial_event
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

    request = bridge_pb2.Request.FromString(rpc_socket.sent[-1])
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


def test_receive_rejects_timer_event_without_timer_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = common_pb2.BridgeEvent(
        session_id=9,
        event_sequence=1,
        type=common_pb2.EVENT_TIMER_SPLIT,
    )
    valid_event = common_pb2.BridgeEvent(
        session_id=9,
        event_sequence=900,
        type=common_pb2.EVENT_TIMER_SPLIT,
        timer_state=common_pb2.TimerState(phase=common_pb2.RUNNING),
    )
    install(
        monkeypatch,
        FakeWebSocket([event.SerializeToString(), valid_event.SerializeToString()]),
        BridgeRespondingWebSocket(9),
    )
    client = BridgeClient()

    with pytest.raises(BridgeProtocolError):
        client.receive()

    assert client.recovery_state is BridgeRecoveryState.RESYNC_REQUIRED
    for operation in (
        lambda: client.receive(timeout_ms=0),
        client.get_run,
        client.start,
    ):
        with pytest.raises(BridgeResyncRequiredError):
            operation()

    client.synchronize()
    assert client.recovery_state is BridgeRecoveryState.HEALTHY
    assert client.receive() == valid_event
    client.close()


@pytest.mark.parametrize(
    "event_type", [common_pb2.EVENT_RUN_CHANGED, common_pb2.EVENT_CONTEXT_CHANGED]
)
def test_receive_accepts_non_timer_events_without_timer_state(
    monkeypatch: pytest.MonkeyPatch,
    event_type: common_pb2.BridgeEventType,
) -> None:
    event = common_pb2.BridgeEvent(session_id=9, event_sequence=1, type=event_type)
    install(monkeypatch, FakeWebSocket([event.SerializeToString()]), FakeWebSocket())
    client = BridgeClient()

    assert client.receive() == event
    assert not event.HasField("timer_state")
    client.close()


@pytest.mark.parametrize("payload", [b"\xff", "text"])
def test_event_decode_protocol_error_requires_resync_and_preserves_error(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes | str,
) -> None:
    install(monkeypatch, FakeWebSocket([payload]), FakeWebSocket())
    client = BridgeClient()

    with pytest.raises(BridgeProtocolError):
        client.receive()

    assert client.recovery_state is BridgeRecoveryState.RESYNC_REQUIRED
    with pytest.raises(BridgeResyncRequiredError):
        client.receive(timeout_ms=0)
    client.close()


def test_event_session_mismatch_precedes_missing_timer_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = common_pb2.BridgeEvent(
        session_id=99,
        event_sequence=1,
        type=common_pb2.EVENT_TIMER_SPLIT,
    )
    rpc_socket = FakeWebSocket(
        [encoded_response(1, session_id=42, get_timer_state=bridge_pb2.GetTimerStateResponse())]
    )
    install(monkeypatch, FakeWebSocket([event.SerializeToString()]), rpc_socket)
    client = BridgeClient()
    client.get_timer_state()

    with pytest.raises(BridgeReconnectRequiredError):
        client.receive()

    assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED
    with pytest.raises(BridgeReconnectRequiredError):
        client.synchronize()
    client.close()


def test_reconnect_returns_state_and_works_after_old_connection_close_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous_event = common_pb2.BridgeEvent(
        session_id=42, event_sequence=45, type=common_pb2.EVENT_RUN_CHANGED
    )
    next_event = common_pb2.BridgeEvent(
        session_id=42, event_sequence=900, type=common_pb2.EVENT_RUN_CHANGED
    )
    old_events = CloseFailingWebSocket([previous_event.SerializeToString()])
    old_rpc = CloseFailingWebSocket()
    new_events = FakeWebSocket([next_event.SerializeToString()])
    new_rpc = BridgeRespondingWebSocket()
    install(monkeypatch, old_events, old_rpc, new_events, new_rpc)
    client = BridgeClient()

    assert client.receive() == previous_event
    state = client.reconnect()
    assert state.session_id == 42
    assert state.attempt.attempt_count == 4
    assert client.get_timer_state().phase == common_pb2.NOT_RUNNING
    assert client.receive() == next_event
    client.close()


def test_reconnect_keeps_old_connections_if_new_rpc_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_events = FakeWebSocket()
    old_timer = common_pb2.TimerState(phase=common_pb2.RUNNING, split_index=2)
    old_rpc = FakeWebSocket(
        [
            encoded_response(
                1, get_timer_state=bridge_pb2.GetTimerStateResponse(timer_state=old_timer)
            )
        ]
    )
    new_events = CloseFailingWebSocket()
    install(
        monkeypatch,
        old_events,
        old_rpc,
        new_events,
        websocket.WebSocketException("rpc connect failed"),
    )
    client = BridgeClient()

    with pytest.raises(BridgeClientError):
        client.reconnect()

    assert client.get_timer_state() == old_timer
    client.close()


def test_reconnect_keeps_old_connections_if_synchronize_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_events = FakeWebSocket()
    old_timer = common_pb2.TimerState(phase=common_pb2.PAUSED, split_index=3)
    old_rpc = FakeWebSocket(
        [
            encoded_response(
                1, get_timer_state=bridge_pb2.GetTimerStateResponse(timer_state=old_timer)
            )
        ]
    )
    new_events = CloseFailingWebSocket()
    inconsistent = synchronization_responses()
    inconsistent[2] = encoded_response(
        3,
        session_id=77,
        get_run=bridge_pb2.GetRunResponse(run=run_pb2.RunState()),
    )
    new_rpc = CloseFailingWebSocket(inconsistent)
    install(monkeypatch, old_events, old_rpc, new_events, new_rpc)
    client = BridgeClient()
    with pytest.raises(BridgeReconnectRequiredError):
        client.reconnect()

    assert client.get_timer_state() == old_timer
    client.close()


def test_synchronize_returns_consistent_snapshot_and_optional_completed_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_socket = FakeWebSocket()
    rpc_socket = BridgeRespondingWebSocket()
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

    with pytest.raises(BridgeReconnectRequiredError):
        client.synchronize()
    assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED

    client.close()


def test_synchronize_error_response_on_new_session_requires_reconnect(
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

    with pytest.raises(BridgeReconnectRequiredError):
        client.synchronize()
    assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED

    client.close()


def test_synchronize_resets_event_sequence_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        common_pb2.BridgeEvent(session_id=42, event_sequence=n, type=common_pb2.EVENT_RUN_CHANGED)
        for n in (100, 500)
    ]
    event_socket = FakeWebSocket([event.SerializeToString() for event in events])
    install(monkeypatch, event_socket, BridgeRespondingWebSocket())
    client = BridgeClient()

    assert client.receive() == events[0]
    client.synchronize()
    assert client.recovery_state is BridgeRecoveryState.HEALTHY
    assert client.receive() == events[1]
    client.close()


@pytest.mark.parametrize(
    "initial_state", [BridgeRecoveryState.HEALTHY, BridgeRecoveryState.RESYNC_REQUIRED]
)
def test_remote_error_during_sync_preserves_existing_recovery_state(
    monkeypatch: pytest.MonkeyPatch,
    initial_state: BridgeRecoveryState,
) -> None:
    events = [
        common_pb2.BridgeEvent(session_id=42, event_sequence=n, type=common_pb2.EVENT_RUN_CHANGED)
        for n in (10, 12)
    ]
    responses = [
        encoded_response(
            1,
            session_id=42,
            get_timer_state=bridge_pb2.GetTimerStateResponse(),
        ),
        encoded_response(
            2,
            session_id=42,
            error=common_pb2.BridgeError(
                code=common_pb2.OPERATION_FAILED,
                message="query failed",
            ),
        ),
    ]
    event_socket = FakeWebSocket([event.SerializeToString() for event in events])
    rpc_socket = FakeWebSocket(responses)
    install(monkeypatch, event_socket, rpc_socket)
    client = BridgeClient()
    if initial_state is BridgeRecoveryState.RESYNC_REQUIRED:
        client.receive()
        with pytest.raises(BridgeResyncRequiredError):
            client.receive()

    with pytest.raises(BridgeRemoteError):
        client.synchronize()
    assert client.recovery_state is initial_state
    client.close()


@pytest.mark.parametrize("start_resync_required", [False, True])
def test_transport_reset_during_synchronize_requires_reconnect(
    monkeypatch: pytest.MonkeyPatch,
    start_resync_required: bool,
) -> None:
    events = [
        common_pb2.BridgeEvent(
            session_id=42,
            event_sequence=sequence,
            type=common_pb2.EVENT_RUN_CHANGED,
        )
        for sequence in (57, 60)
    ]
    event_socket = FakeWebSocket([event.SerializeToString() for event in events])
    rpc_socket = FakeWebSocket(
        [
            encoded_response(
                1,
                session_id=42,
                get_timer_state=bridge_pb2.GetTimerStateResponse(),
            )
        ],
        timeout=True,
    )
    replacement = FakeWebSocket()
    install(monkeypatch, event_socket, rpc_socket, replacement)
    client = BridgeClient()

    if start_resync_required:
        assert client.receive() == events[0]
        with pytest.raises(BridgeResyncRequiredError):
            client.receive()
        assert client.recovery_state is BridgeRecoveryState.RESYNC_REQUIRED

    with pytest.raises(BridgeResponseTimeoutError):
        client.synchronize()

    assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED
    assert replacement.sent == []
    for operation in (
        client.get_timer_state,
        client.split,
        lambda: client.receive(timeout_ms=0),
        client.synchronize,
    ):
        with pytest.raises(BridgeReconnectRequiredError):
            operation()
    assert replacement.sent == []
    client.close()


def test_sync_session_different_from_known_rpc_session_requires_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        encoded_response(
            1,
            session_id=42,
            get_timer_state=bridge_pb2.GetTimerStateResponse(),
        ),
        *synchronization_responses(99, start_request_id=2),
    ]
    install(monkeypatch, FakeWebSocket(), FakeWebSocket(responses))
    client = BridgeClient()

    client.get_timer_state()
    with pytest.raises(BridgeReconnectRequiredError):
        client.synchronize()
    assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED
    client.close()


def test_sequence_gap_can_recover_with_synchronize_and_new_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        common_pb2.BridgeEvent(session_id=42, event_sequence=n, type=common_pb2.EVENT_RUN_CHANGED)
        for n in (57, 60, 900)
    ]
    event_socket = FakeWebSocket([event.SerializeToString() for event in events])
    rpc_socket = FakeWebSocket(synchronization_responses())
    install(monkeypatch, event_socket, rpc_socket)
    client = BridgeClient()

    assert client.receive() == events[0]
    with pytest.raises(BridgeResyncRequiredError):
        client.receive()
    assert client.recovery_state is BridgeRecoveryState.RESYNC_REQUIRED
    with pytest.raises(BridgeResyncRequiredError):
        client.get_run()

    client.synchronize()
    assert client.recovery_state is BridgeRecoveryState.HEALTHY
    assert client.receive() == events[2]
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


def test_rpc_session_change_requires_reconnect_before_more_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_events = FakeWebSocket()
    old_rpc = FakeWebSocket(
        [
            encoded_response(1, session_id=42, get_timer_state=bridge_pb2.GetTimerStateResponse()),
            encoded_response(2, session_id=99, get_timer_state=bridge_pb2.GetTimerStateResponse()),
        ]
    )
    new_events = FakeWebSocket()
    new_rpc = BridgeRespondingWebSocket(99)
    install(monkeypatch, old_events, old_rpc, new_events, new_rpc)
    client = BridgeClient()

    client.get_timer_state()
    with pytest.raises(BridgeReconnectRequiredError):
        client.get_timer_state()
    assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED
    with pytest.raises(BridgeReconnectRequiredError):
        client.get_timer_state()
    with pytest.raises(BridgeReconnectRequiredError):
        client.synchronize()

    state = client.reconnect()
    assert state.session_id == 99
    assert client.recovery_state is BridgeRecoveryState.HEALTHY
    client.close()


def test_initial_malformed_rpc_response_preserves_protocol_error_and_healthy_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    rpc_socket = FakeWebSocket([b"\xff"])
    install(monkeypatch, FakeWebSocket(), rpc_socket)
    client = BridgeClient()

    with pytest.raises(BridgeProtocolError):
        client.get_timer_state()

    assert client.recovery_state is BridgeRecoveryState.HEALTHY
    client.close()


@pytest.mark.parametrize(
    ("failed_socket", "expected_error"),
    [
        (FakeWebSocket(timeout=True), BridgeResponseTimeoutError),
        (
            FakeWebSocket([websocket.WebSocketConnectionClosedException("closed")]),
            BridgeClientError,
        ),
        (FakeWebSocket([websocket.WebSocketException("transport error")]), BridgeClientError),
    ],
)
def test_initial_rpc_transport_reset_requires_reconnect_and_preserves_error(
    monkeypatch: pytest.MonkeyPatch,
    failed_socket: FakeWebSocket,
    expected_error: type[Exception],
) -> None:
    replacement = FakeWebSocket()
    new_rpc = BridgeRespondingWebSocket(99)
    install(
        monkeypatch,
        FakeWebSocket(),
        failed_socket,
        replacement,
        FakeWebSocket(),
        new_rpc,
    )
    client = BridgeClient()

    with pytest.raises(expected_error):
        client.split()

    assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED
    assert len(failed_socket.sent) == 1
    assert replacement.sent == []
    for operation in (
        client.get_timer_state,
        client.split,
        lambda: client.receive(timeout_ms=0),
        client.synchronize,
    ):
        with pytest.raises(BridgeReconnectRequiredError):
            operation()
    assert replacement.sent == []

    state = client.reconnect()
    assert state.session_id == 99
    assert client.recovery_state is BridgeRecoveryState.HEALTHY
    assert client.get_timer_state().phase == common_pb2.NOT_RUNNING
    assert not client.split().ListFields()
    client.close()


def test_rpc_error_response_session_change_requires_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rpc_socket = FakeWebSocket(
        [
            encoded_response(1, session_id=42, get_timer_state=bridge_pb2.GetTimerStateResponse()),
            encoded_response(
                2,
                session_id=99,
                error=common_pb2.BridgeError(
                    code=common_pb2.OPERATION_FAILED,
                    message="new runtime unavailable",
                ),
            ),
        ]
    )
    install(monkeypatch, FakeWebSocket(), rpc_socket)
    client = BridgeClient()

    client.get_timer_state()
    with pytest.raises(BridgeReconnectRequiredError):
        client.start()
    assert client.session_id == 99
    assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED
    client.close()


def test_rpc_event_session_mismatch_requires_reconnect(
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
    with pytest.raises(BridgeReconnectRequiredError):
        client.receive()
    client.close()


def test_event_connection_loss_requires_reconnect_without_rewriting_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(
        monkeypatch,
        FakeWebSocket([websocket.WebSocketConnectionClosedException("event socket closed")]),
        FakeWebSocket(),
    )
    client = BridgeClient()

    with pytest.raises(BridgeConnectionLostError):
        client.receive()
    assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED
    with pytest.raises(BridgeReconnectRequiredError):
        client.receive()
    client.close()


def test_event_session_change_requires_reconnect_and_blocks_synchronize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        common_pb2.BridgeEvent(session_id=42, event_sequence=1, type=common_pb2.EVENT_RUN_CHANGED),
        common_pb2.BridgeEvent(session_id=77, event_sequence=2, type=common_pb2.EVENT_RUN_CHANGED),
    ]
    install(
        monkeypatch, FakeWebSocket([event.SerializeToString() for event in events]), FakeWebSocket()
    )
    client = BridgeClient()

    assert client.receive() == events[0]
    with pytest.raises(BridgeReconnectRequiredError):
        client.receive()
    assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED
    with pytest.raises(BridgeReconnectRequiredError):
        client.synchronize()
    client.close()


def test_reconnect_first_event_must_match_new_rpc_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = common_pb2.BridgeEvent(
        session_id=42, event_sequence=57, type=common_pb2.EVENT_RUN_CHANGED
    )
    install(
        monkeypatch,
        FakeWebSocket(),
        FakeWebSocket(),
        FakeWebSocket([event.SerializeToString()]),
        BridgeRespondingWebSocket(99),
    )
    client = BridgeClient()

    assert client.reconnect().session_id == 99
    with pytest.raises(BridgeReconnectRequiredError):
        client.receive()
    assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED
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
            BridgeResyncRequiredError,
            BridgeRecoveryState.RESYNC_REQUIRED,
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
            BridgeReconnectRequiredError,
            BridgeRecoveryState.RECONNECT_REQUIRED,
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
            BridgeResyncRequiredError,
            BridgeRecoveryState.RESYNC_REQUIRED,
        ),
    ]
    for events, _, error_type, expected_state in cases:
        event_socket = FakeWebSocket([event.SerializeToString() for event in events])
        install(monkeypatch, event_socket, FakeWebSocket())
        client = BridgeClient()
        if len(events) > 1:
            client.receive()
        with pytest.raises(error_type):
            client.receive()
        assert client.recovery_state is expected_state
        client.close()


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
    assert client.recovery_state is BridgeRecoveryState.HEALTHY

    client.close()


def test_close_is_idempotent_and_rejects_operations_and_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(monkeypatch, FakeWebSocket(), FakeWebSocket())
    client = BridgeClient()
    client.close()
    client.close()

    with pytest.raises(BridgeClientError):
        client.get_timer_state()
    with pytest.raises(BridgeClientError):
        _ = client.rpc
    with pytest.raises(BridgeClientError):
        _ = client.events
    with pytest.raises(BridgeClientError):
        _ = client.session_id
