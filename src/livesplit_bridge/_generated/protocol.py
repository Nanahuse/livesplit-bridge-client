# Generated from LiveSplit.Bridge@3397fc570b37d902307532a914a2874c425c2b2a
# datamodel-code-generator 0.86.0; Ruff 0.16.4.
# DO NOT EDIT. Run: uv run tools/update_protocol.py

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, StrictBool, StrictInt, StrictStr


class QueryMethod(StrEnum):
    GET_TIMER_STATE = "get_timer_state"
    GET_RUN = "get_run"
    GET_RUN_ICONS = "get_run_icons"
    GET_ATTEMPT = "get_attempt"
    GET_CONTEXT_STATE = "get_context_state"
    GET_COMPLETED_COUNT = "get_completed_count"


class QueryRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    request_id: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    method: QueryMethod


class TimerOperation(StrEnum):
    START = "start"
    SPLIT = "split"
    SKIP = "skip"
    UNDO = "undo"
    RESET = "reset"
    PAUSE = "pause"
    RESUME = "resume"


class TimerParams(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    operation: TimerOperation


class TimerRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    request_id: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    method: Literal["timer_operation"]
    params: TimerParams


class GameControlOperation(StrEnum):
    INITIALIZE = "initialize"
    PAUSE = "pause"
    RESUME = "resume"


class GameControlParams(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    operation: GameControlOperation


class GameControlRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    request_id: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    method: Literal["game_time_operation"]
    params: GameControlParams


class GameSetParams(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    operation: Literal["set"]
    ticks: Annotated[StrictInt, Field(ge=-9223372036854775808, le=9223372036854775807)]


class GameSetRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    request_id: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    method: Literal["game_time_operation"]
    params: GameSetParams


class RpcRequest(RootModel[QueryRequest | TimerRequest | GameControlRequest | GameSetRequest]):
    root: QueryRequest | TimerRequest | GameControlRequest | GameSetRequest


class TimerPhase(StrEnum):
    UNSPECIFIED = "unspecified"
    NOT_RUNNING = "not_running"
    RUNNING = "running"
    PAUSED = "paused"
    ENDED = "ended"


class TimerState(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    phase: TimerPhase
    split_index: Annotated[StrictInt, Field(ge=-2147483648, le=2147483647)]
    real_time_ticks: Annotated[StrictInt, Field(ge=-9223372036854775808, le=9223372036854775807)]
    game_time_ticks: Annotated[
        StrictInt | None, Field(ge=-9223372036854775808, le=9223372036854775807)
    ]
    is_game_time_initialized: StrictBool
    is_game_time_paused: StrictBool


class TimerStateResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    request_id: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    session_id: Annotated[StrictInt, Field(ge=1, le=4294967295)]
    result: TimerState


class RunMetadata(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    run_id: StrictStr | None
    platform_name: StrictStr | None
    region_name: StrictStr | None
    uses_emulator: StrictBool
    variables: dict[str, StrictStr]


class TimeValue(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    real_time_ticks: Annotated[
        StrictInt | None, Field(ge=-9223372036854775808, le=9223372036854775807)
    ]
    game_time_ticks: Annotated[
        StrictInt | None, Field(ge=-9223372036854775808, le=9223372036854775807)
    ]


class ComparisonTime(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: StrictStr
    time: TimeValue


class SegmentInfo(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    index: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    name: StrictStr
    comparisons: list[ComparisonTime]
    best_segment_time: TimeValue


class RunState(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    game_name: StrictStr
    category_name: StrictStr
    offset_ticks: Annotated[StrictInt, Field(ge=-9223372036854775808, le=9223372036854775807)]
    file_path: StrictStr | None
    layout_path: StrictStr | None
    metadata: RunMetadata | None
    comparisons: list[StrictStr]
    segments: list[SegmentInfo]


class RunStateResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    request_id: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    session_id: Annotated[StrictInt, Field(ge=1, le=4294967295)]
    result: RunState


class RunIcons(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    game_icon: StrictStr | None
    """
    Base64-encoded PNG image; null when absent.
    """
    segment_icons: list[StrictStr | None]
    """
    Segment icons in Run order, as Base64-encoded PNG images; null entries when absent.
    """


class RunIconsResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    request_id: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    session_id: Annotated[StrictInt, Field(ge=1, le=4294967295)]
    result: RunIcons


class AttemptSegment(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    index: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    split_time: TimeValue
    custom_variables: dict[str, StrictStr]


class AttemptState(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    attempt_count: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    segments: list[AttemptSegment]


class AttemptStateResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    request_id: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    session_id: Annotated[StrictInt, Field(ge=1, le=4294967295)]
    result: AttemptState


class TimingMethod(StrEnum):
    UNSPECIFIED = "unspecified"
    REAL_TIME = "real_time"
    GAME_TIME = "game_time"


class ContextState(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    current_timing_method: TimingMethod
    current_comparison: StrictStr
    custom_variables: dict[str, StrictStr]


class ContextStateResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    request_id: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    session_id: Annotated[StrictInt, Field(ge=1, le=4294967295)]
    result: ContextState


class CompletedCount(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    completed_count: Annotated[StrictInt, Field(ge=0, le=4294967295)]


class CompletedCountResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    request_id: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    session_id: Annotated[StrictInt, Field(ge=1, le=4294967295)]
    result: CompletedCount


class ControlSuccessResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    request_id: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    session_id: Annotated[StrictInt, Field(ge=1, le=4294967295)]
    result: None


class BridgeErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    INVALID_ARGUMENT = "invalid_argument"
    OPERATION_FAILED = "operation_failed"
    INTERNAL_ERROR = "internal_error"
    PERMISSION_DENIED = "permission_denied"


class BridgeError(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    code: BridgeErrorCode
    message: StrictStr


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    request_id: Annotated[StrictInt, Field(ge=0, le=4294967295)]
    session_id: Annotated[StrictInt, Field(ge=1, le=4294967295)]
    error: BridgeError


class RpcResponse(
    RootModel[
        TimerStateResponse
        | RunStateResponse
        | RunIconsResponse
        | AttemptStateResponse
        | ContextStateResponse
        | CompletedCountResponse
        | ControlSuccessResponse
        | ErrorResponse
    ]
):
    root: (
        TimerStateResponse
        | RunStateResponse
        | RunIconsResponse
        | AttemptStateResponse
        | ContextStateResponse
        | CompletedCountResponse
        | ControlSuccessResponse
        | ErrorResponse
    )


class TimerEventType(StrEnum):
    TIMER_STARTED = "timer_started"
    TIMER_SPLIT = "timer_split"
    TIMER_SKIPPED = "timer_skipped"
    TIMER_UNDO = "timer_undo"
    TIMER_PHASE_CHANGED = "timer_phase_changed"


class TimerEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    session_id: Annotated[StrictInt, Field(ge=1, le=4294967295)]
    event_sequence: Annotated[StrictInt, Field(ge=1, le=4294967295)]
    type: TimerEventType
    timer_state: TimerState


class ResetEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    session_id: Annotated[StrictInt, Field(ge=1, le=4294967295)]
    event_sequence: Annotated[StrictInt, Field(ge=1, le=4294967295)]
    type: Literal["timer_reset"]
    timer_state: TimerState | None


class ChangedEventType(StrEnum):
    RUN_CHANGED = "run_changed"
    CONTEXT_CHANGED = "context_changed"


class ChangedEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    session_id: Annotated[StrictInt, Field(ge=1, le=4294967295)]
    event_sequence: Annotated[StrictInt, Field(ge=1, le=4294967295)]
    type: ChangedEventType
    timer_state: None


class BridgeEvent(RootModel[TimerEvent | ResetEvent | ChangedEvent]):
    root: TimerEvent | ResetEvent | ChangedEvent


class EventType(StrEnum):
    TIMER_STARTED = "timer_started"
    TIMER_SPLIT = "timer_split"
    TIMER_SKIPPED = "timer_skipped"
    TIMER_UNDO = "timer_undo"
    TIMER_PHASE_CHANGED = "timer_phase_changed"
    TIMER_RESET = "timer_reset"
    RUN_CHANGED = "run_changed"
    CONTEXT_CHANGED = "context_changed"


class GameTimeOperation(StrEnum):
    INITIALIZE = "initialize"
    PAUSE = "pause"
    RESUME = "resume"
    SET = "set"


class GameTimeRequest(RootModel[GameControlRequest | GameSetRequest]):
    root: GameControlRequest | GameSetRequest


class SuccessResponse(
    RootModel[
        TimerStateResponse
        | RunStateResponse
        | RunIconsResponse
        | AttemptStateResponse
        | ContextStateResponse
        | CompletedCountResponse
        | ControlSuccessResponse
    ]
):
    root: (
        TimerStateResponse
        | RunStateResponse
        | RunIconsResponse
        | AttemptStateResponse
        | ContextStateResponse
        | CompletedCountResponse
        | ControlSuccessResponse
    )


class Model(
    RootModel[
        RpcRequest
        | RpcResponse
        | BridgeEvent
        | EventType
        | GameTimeOperation
        | GameTimeRequest
        | SuccessResponse
    ]
):
    root: (
        RpcRequest
        | RpcResponse
        | BridgeEvent
        | EventType
        | GameTimeOperation
        | GameTimeRequest
        | SuccessResponse
    )
