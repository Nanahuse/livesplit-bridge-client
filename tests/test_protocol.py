from __future__ import annotations

from livesplit_bridge import bridge_pb2, common_pb2, run_pb2


def test_v3_timer_and_run_state_are_constructible() -> None:
    timer = common_pb2.TimerState(
        phase=common_pb2.RUNNING,
        split_index=3,
        real_time_ticks=123,
        game_time_ticks=456,
    )
    run = run_pb2.RunState(
        game_name="Super Mario World",
        category_name="11 Exit",
        metadata=run_pb2.RunMetadata(run_id="run-id", variables={"seed": "42"}),
        comparisons=["Personal Best"],
        segments=[
            run_pb2.SegmentInfo(
                index=0,
                name="Yoshi's House",
                comparisons=[
                    run_pb2.ComparisonTime(
                        name="Personal Best", time=common_pb2.TimeValue(real_time_ticks=10)
                    )
                ],
            )
        ],
    )

    assert timer.phase == common_pb2.RUNNING
    assert timer.game_time_ticks == 456
    assert run.game_name == "Super Mario World"
    assert run.metadata.variables["seed"] == "42"
    assert run.segments[0].comparisons[0].time.real_time_ticks == 10


def test_context_and_completed_count_are_v3_queries() -> None:
    context = common_pb2.ContextState(
        current_timing_method=common_pb2.GAME_TIME,
        current_comparison="Personal Best",
        custom_variables={"character": "Yoshi"},
    )
    completed = common_pb2.CompletedCount(completed_count=7)
    request = bridge_pb2.Request(get_context_state=bridge_pb2.GetContextStateRequest())

    assert context.current_timing_method == common_pb2.GAME_TIME
    assert context.custom_variables["character"] == "Yoshi"
    assert completed.completed_count == 7
    assert request.WhichOneof("body") == "get_context_state"


def test_v3_response_envelope_and_empty_operation_response() -> None:
    response = bridge_pb2.Response(
        protocol_version=3,
        request_id=9,
        session_id=11,
        operation=common_pb2.OperationResponse(),
    )

    assert response.protocol_version == 3
    assert response.request_id == 9
    assert response.session_id == 11
    assert response.HasField("operation")
    assert not response.operation.ListFields()


def test_event_types_and_optional_timer_state() -> None:
    timer_event = common_pb2.BridgeEvent(
        session_id=1,
        event_sequence=2,
        type=common_pb2.EVENT_TIMER_SPLIT,
        timer_state=common_pb2.TimerState(phase=common_pb2.ENDED),
    )
    run_event = common_pb2.BridgeEvent(
        session_id=1,
        event_sequence=3,
        type=common_pb2.EVENT_RUN_CHANGED,
    )

    assert timer_event.HasField("timer_state")
    assert timer_event.timer_state.phase == common_pb2.ENDED
    assert not run_event.HasField("timer_state")
