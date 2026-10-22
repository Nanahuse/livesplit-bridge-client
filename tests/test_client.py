from __future__ import annotations

import json
from typing import Any

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
    EventType,
)
from livesplit_bridge import rpc as rpc_module

from .support import (
    FakeConnections,
    FakeWebSocket,
    RequestAwareBridgeSocket,
    event,
    query_result,
    response_scenario,
    timer,
)


def install(
    monkeypatch: pytest.MonkeyPatch, *sockets: FakeWebSocket | Exception
) -> FakeConnections:
    connections = FakeConnections(*sockets)
    monkeypatch.setattr(rpc_module.websocket, "create_connection", connections)
    return connections


class CloseFailingSocket(RequestAwareBridgeSocket):
    def close(self) -> None:
        super().close()
        raise RuntimeError("close failed")


def test_initial_sync_keeps_buffered_events_and_queries_no_icons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial_event = event(74)
    rpc = RequestAwareBridgeSocket()
    connections = install(monkeypatch, FakeWebSocket([initial_event.model_dump_json()]), rpc)
    with BridgeClient() as client:
        state = client.synchronize(include_completed_count=True)
        assert state.session_id == 42
        assert state.timer_state == timer()
        assert state.attempt.attempt_count == 4
        assert state.run.game_name == "Game"
        assert state.context_state.current_comparison == "Personal Best"
        assert state.completed_count is not None
        assert state.completed_count.completed_count == 9
        assert client.receive() == initial_event
        assert client.recovery_state is BridgeRecoveryState.HEALTHY
    assert [json.loads(message)["method"] for message in rpc.sent] == [
        "get_timer_state",
        "get_attempt",
        "get_run",
        "get_context_state",
        "get_completed_count",
    ]
    assert connections.endpoints[0].endswith("/v4/events")
    assert connections.endpoints[1].endswith("/v4/rpc")


def test_integrated_queries_controls_and_on_demand_icons(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = RequestAwareBridgeSocket()
    install(monkeypatch, FakeWebSocket(), rpc)
    with BridgeClient() as client:
        assert client.get_timer_state() == timer()
        assert client.get_run().game_name == "Game"
        assert client.get_attempt().attempt_count == 4
        assert client.get_context_state().current_comparison == "Personal Best"
        assert client.get_completed_count().completed_count == 9
        assert client.start() is None
        assert client.set_game_time_ticks(-100) is None
        assert client.get_run_icons().segment_icons == [None, None]
        assert client.get_run_icons().game_icon is None
        assert client.session_id == 42
    assert [json.loads(message)["method"] for message in rpc.sent].count("get_run_icons") == 2


@pytest.mark.parametrize("kind", list(EventType))
def test_event_kinds_and_iteration(monkeypatch: pytest.MonkeyPatch, kind: EventType) -> None:
    state = (
        None
        if kind in (EventType.RUN_CHANGED, EventType.CONTEXT_CHANGED, EventType.TIMER_RESET)
        else timer(phase="running")
    )
    first = event(1, kind=kind, state=state)
    second = event(2)
    install(
        monkeypatch,
        FakeWebSocket([first.model_dump_json(), second.model_dump_json()]),
        RequestAwareBridgeSocket(),
    )
    with BridgeClient() as client:
        assert client.receive() == first
        assert iter(client) is client
        assert next(client) == second


@pytest.mark.parametrize(
    "sequences", [(57, 60, 900), (10, 10, 12), (10, 9, 900), (2**32 - 1, 2, 100)]
)
def test_gaps_duplicates_and_reordering_require_sync(
    monkeypatch: pytest.MonkeyPatch,
    sequences: tuple[int, int, int],
) -> None:
    events = [event(n) for n in sequences]
    install(
        monkeypatch,
        FakeWebSocket([e.model_dump_json() for e in events]),
        RequestAwareBridgeSocket(),
    )
    with BridgeClient() as client:
        assert client.receive() == events[0]
        with pytest.raises(BridgeResyncRequiredError):
            client.receive()
        assert client.recovery_state is BridgeRecoveryState.RESYNC_REQUIRED
        for operation in (client.get_run, client.start, lambda: client.receive(timeout_ms=0)):
            with pytest.raises(BridgeResyncRequiredError):
                operation()
        state = client.synchronize()
        assert state.completed_count is None
        assert client.recovery_state is BridgeRecoveryState.HEALTHY
        assert client.receive() == events[2]


def test_sequence_wrap_and_arbitrary_first_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [event(n) for n in (2**32 - 2, 2**32 - 1, 1, 2)]
    install(monkeypatch, FakeWebSocket([e.model_dump_json() for e in events]), FakeWebSocket())
    with BridgeClient() as client:
        for expected in events:
            assert client.receive() == expected
        assert client.recovery_state is BridgeRecoveryState.HEALTHY


@pytest.mark.parametrize(
    "payload",
    [
        b"binary",
        "invalid",
        '{"session_id":42,"event_sequence":1,"type":"timer_split"}',
        '{"session_id":42,"event_sequence":1,"type":"timer_split","timer_state":null}',
        '{"session_id":42,"event_sequence":1,"type":"unknown","timer_state":null}',
        '{"session_id":42,"event_sequence":0,"type":"run_changed","timer_state":null}',
    ],
)
def test_malformed_event_preserves_protocol_error_and_requires_resync(
    monkeypatch: pytest.MonkeyPatch,
    payload: str | bytes,
) -> None:
    valid = event(900)
    install(
        monkeypatch, FakeWebSocket([payload, valid.model_dump_json()]), RequestAwareBridgeSocket()
    )
    with BridgeClient() as client:
        with pytest.raises(BridgeProtocolError):
            client.receive()
        assert client.recovery_state is BridgeRecoveryState.RESYNC_REQUIRED
        client.synchronize()
        assert client.receive() == valid


@pytest.mark.parametrize("before_rpc", [True, False])
def test_rpc_and_events_must_share_session(
    monkeypatch: pytest.MonkeyPatch, before_rpc: bool
) -> None:
    install(
        monkeypatch,
        FakeWebSocket([event(session_id=77).model_dump_json()]),
        RequestAwareBridgeSocket(),
    )
    with BridgeClient() as client:
        if before_rpc:
            client.get_timer_state()
        else:
            client.receive()
        with pytest.raises(BridgeReconnectRequiredError):
            client.receive() if before_rpc else client.get_timer_state()
        assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED
        with pytest.raises(BridgeReconnectRequiredError):
            client.synchronize()


def test_event_session_change_requires_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    install(
        monkeypatch,
        FakeWebSocket([event().model_dump_json(), event(2, session_id=77).model_dump_json()]),
        FakeWebSocket(),
    )
    with BridgeClient() as client:
        client.receive()
        with pytest.raises(BridgeReconnectRequiredError):
            client.receive()
        assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED


@pytest.mark.parametrize("error_response", [False, True])
def test_rpc_session_change_including_error_response_requires_reconnect(
    monkeypatch: pytest.MonkeyPatch,
    error_response: bool,
) -> None:
    changed = response_scenario(
        session_id=99,
        **(
            {"error": {"code": "operation_failed", "message": "runtime changed"}}
            if error_response
            else {"result": query_result("get_timer_state")}
        ),
    )
    rpc = RequestAwareBridgeSocket(
        scenarios={
            "get_timer_state": [
                response_scenario(result=query_result("get_timer_state")),
                changed,
            ]
        }
    )
    install(monkeypatch, FakeWebSocket(), rpc, FakeWebSocket(), RequestAwareBridgeSocket(99))
    with BridgeClient() as client:
        client.get_timer_state()
        with pytest.raises(BridgeReconnectRequiredError):
            client.get_timer_state()
        assert client.session_id == 99
        with pytest.raises(BridgeReconnectRequiredError):
            client.start()
        state = client.reconnect()
        assert state.session_id == 99
        assert client.recovery_state is BridgeRecoveryState.HEALTHY


@pytest.mark.parametrize("error_response", [False, True])
def test_synchronize_never_returns_partial_state_on_session_change(
    monkeypatch: pytest.MonkeyPatch,
    error_response: bool,
) -> None:
    body = (
        {"error": {"code": "operation_failed", "message": "changed"}}
        if error_response
        else {"result": query_result("get_run")}
    )
    rpc = RequestAwareBridgeSocket(scenarios={"get_run": response_scenario(session_id=77, **body)})
    install(monkeypatch, FakeWebSocket(), rpc)
    with BridgeClient() as client:
        with pytest.raises(BridgeReconnectRequiredError):
            client.synchronize()
        assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED


@pytest.mark.parametrize("start_resync_required", [False, True])
@pytest.mark.parametrize("failure", ["timeout", "malformed", "remote"])
def test_sync_failure_preserves_error_and_recovery_state(
    monkeypatch: pytest.MonkeyPatch,
    start_resync_required: bool,
    failure: str,
) -> None:
    scenario: Any = {
        "timeout": websocket.WebSocketTimeoutException("timed out"),
        "malformed": response_scenario(result={}),
        "remote": response_scenario(error={"code": "operation_failed", "message": "failed"}),
    }[failure]
    rpc = RequestAwareBridgeSocket(scenarios={"get_attempt": scenario})
    install(
        monkeypatch, FakeWebSocket([event(10).model_dump_json(), event(12).model_dump_json()]), rpc
    )
    with BridgeClient() as client:
        if start_resync_required:
            client.receive()
            with pytest.raises(BridgeResyncRequiredError):
                client.receive()
        previous = client.recovery_state
        expected = {
            "timeout": BridgeResponseTimeoutError,
            "malformed": BridgeProtocolError,
            "remote": BridgeRemoteError,
        }[failure]
        with pytest.raises(expected):
            client.synchronize()
        assert client.recovery_state is (
            previous if failure == "remote" else BridgeRecoveryState.RECONNECT_REQUIRED
        )


@pytest.mark.parametrize(
    ("failed", "error_type"),
    [
        (FakeWebSocket(timeout=True), BridgeResponseTimeoutError),
        (FakeWebSocket([b"binary"]), BridgeProtocolError),
        (FakeWebSocket([(websocket.ABNF.OPCODE_CLOSE, b"")]), BridgeClientError),
        (FakeWebSocket([websocket.WebSocketException("failed")]), BridgeClientError),
    ],
)
def test_rpc_failure_blocks_all_operations_until_reconnect_without_replay(
    monkeypatch: pytest.MonkeyPatch,
    failed: FakeWebSocket,
    error_type: type[Exception],
) -> None:
    replacement = RequestAwareBridgeSocket(99)
    connections = install(monkeypatch, FakeWebSocket(), failed, FakeWebSocket(), replacement)
    with BridgeClient() as client:
        with pytest.raises(error_type):
            client.split()
        assert len(failed.sent) == 1
        assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED
        for operation in (client.get_run, client.split, client.receive, client.synchronize):
            with pytest.raises(BridgeReconnectRequiredError):
                operation()
        assert len(connections.endpoints) == 2
        assert client.reconnect().session_id == 99
        assert all(
            json.loads(message)["method"] != "timer_operation" for message in replacement.sent
        )
        client.split()


def test_event_disconnect_requires_reconnect_and_stays_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(monkeypatch, FakeWebSocket([(websocket.ABNF.OPCODE_CLOSE, b"")]), FakeWebSocket())
    with BridgeClient() as client:
        with pytest.raises(BridgeConnectionLostError):
            client.receive()
        assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED
        with pytest.raises(BridgeReconnectRequiredError):
            client.receive()


@pytest.mark.parametrize("failure", ["connect", "sync"])
def test_failed_reconnect_keeps_old_pair_and_closes_new_pair(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    old_events, old_rpc = FakeWebSocket(), RequestAwareBridgeSocket()
    new_events = CloseFailingSocket()
    new_rpc = (
        websocket.WebSocketException("failed")
        if failure == "connect"
        else CloseFailingSocket(
            scenarios={"get_run": response_scenario(session_id=77, result=query_result("get_run"))}
        )
    )
    install(monkeypatch, old_events, old_rpc, new_events, new_rpc)
    with BridgeClient() as client:
        with pytest.raises(BridgeClientError):
            client.reconnect()
        assert new_events.close_called
        if isinstance(new_rpc, FakeWebSocket):
            assert new_rpc.close_called
        assert not old_events.close_called
        assert client.get_timer_state() == timer()


def test_reconnect_closes_old_pair_and_checks_first_event_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_events, old_rpc = CloseFailingSocket(), CloseFailingSocket()
    install(
        monkeypatch,
        old_events,
        old_rpc,
        FakeWebSocket([event(900, session_id=42).model_dump_json()]),
        RequestAwareBridgeSocket(99),
    )
    with BridgeClient() as client:
        assert client.reconnect().session_id == 99
        assert old_events.close_called and old_rpc.close_called
        with pytest.raises(BridgeReconnectRequiredError):
            client.receive()


def test_remote_error_does_not_require_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    rpc = RequestAwareBridgeSocket(
        scenarios={
            "timer_operation": response_scenario(
                error={"code": "permission_denied", "message": "denied"}
            )
        }
    )
    install(monkeypatch, FakeWebSocket(), rpc)
    with BridgeClient() as client:
        with pytest.raises(BridgeRemoteError) as error:
            client.reset()
        assert error.value.code == "permission_denied"
        assert client.recovery_state is BridgeRecoveryState.HEALTHY
        assert client.get_timer_state() == timer()


def test_close_and_partial_initialization_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    events = CloseFailingSocket()
    install(monkeypatch, events, websocket.WebSocketException("failed"))
    with pytest.raises(BridgeClientError):
        BridgeClient()
    assert events.close_called
    install(monkeypatch, FakeWebSocket(), FakeWebSocket())
    client = BridgeClient()
    client.close()
    client.close()
    for operation in (client.get_run, client.receive, client.reconnect, client.synchronize):
        with pytest.raises(BridgeClientError):
            operation()
    with pytest.raises(BridgeClientError):
        _ = client.session_id
