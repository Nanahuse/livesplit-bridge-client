from __future__ import annotations

from livesplit_bridge import bridge_pb2, common_pb2, run_pb2


def test_timer_state_is_constructible() -> None:
    state = common_pb2.TimerState(
        session_id=1,
        state_revision=2,
        phase=common_pb2.RUNNING,
        split_index=3,
        run_revision=4,
        attempt_revision=5,
        runtime_revision=6,
    )

    assert state.session_id == 1
    assert state.state_revision == 2
    assert state.phase == common_pb2.RUNNING
    assert state.split_index == 3
    assert state.run_revision == 4
    assert state.attempt_revision == 5
    assert state.runtime_revision == 6


def test_run_state_is_constructible() -> None:
    state = run_pb2.RunState(
        session_id=1,
        run_revision=2,
        game_name="Super Mario World",
        category_name="11 Exit",
    )

    assert state.session_id == 1
    assert state.run_revision == 2
    assert state.game_name == "Super Mario World"
    assert state.category_name == "11 Exit"


def test_run_state_optional_presence() -> None:
    state = run_pb2.RunState()

    assert not state.HasField("file_path")
    assert not state.HasField("layout_path")

    state.file_path = "test.lss"

    assert state.HasField("file_path")


def test_attempt_state_is_constructible() -> None:
    state = common_pb2.AttemptState(
        session_id=1,
        attempt_revision=2,
        attempt_count=3,
        completed_count=4,
    )

    assert state.session_id == 1
    assert state.attempt_revision == 2
    assert state.attempt_count == 3
    assert state.completed_count == 4


def test_runtime_state_is_constructible() -> None:
    state = common_pb2.RuntimeState(
        session_id=1,
        runtime_revision=2,
        current_timing_method=common_pb2.REAL_TIME,
        current_comparison="Personal Best",
        global_hotkeys_enabled=True,
    )

    assert state.session_id == 1
    assert state.runtime_revision == 2
    assert state.current_timing_method == common_pb2.REAL_TIME
    assert state.current_comparison == "Personal Best"
    assert state.global_hotkeys_enabled


def test_attach_response_is_constructible() -> None:
    response = bridge_pb2.AttachResponse(
        session_id=1,
        timer_state=common_pb2.TimerState(session_id=1, phase=common_pb2.NOT_RUNNING),
    )

    assert response.session_id == 1
    assert response.HasField("timer_state")


def test_bridge_event_optional_timer_state() -> None:
    event = common_pb2.BridgeEvent(
        session_id=1,
        event_sequence=2,
        type=common_pb2.EVENT_TIMER_SPLIT,
        timer_state=common_pb2.TimerState(session_id=1, phase=common_pb2.RUNNING),
    )
    heartbeat = common_pb2.BridgeEvent(type=common_pb2.EVENT_HEARTBEAT)

    assert event.type == common_pb2.EVENT_TIMER_SPLIT
    assert event.HasField("timer_state")
    assert not heartbeat.HasField("timer_state")
