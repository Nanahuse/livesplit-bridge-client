"""Typed JSON v4 contracts, maintained against the pinned Bridge C# DTOs."""

from __future__ import annotations

import base64
import binascii
from enum import StrEnum
from typing import Annotated, Generic, Literal, Self, TypeVar

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    WithJsonSchema,
    model_validator,
)

UINT32_MAX = 2**32 - 1
UInt32 = Annotated[int, Field(ge=0, le=UINT32_MAX)]
NonZeroUInt32 = Annotated[int, Field(ge=1, le=UINT32_MAX)]
Int32 = Annotated[int, Field(ge=-(2**31), le=2**31 - 1)]
Ticks = Annotated[int, Field(ge=-(2**63), le=2**63 - 1)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TimerPhase(StrEnum):
    UNSPECIFIED = "unspecified"
    NOT_RUNNING = "not_running"
    RUNNING = "running"
    PAUSED = "paused"
    ENDED = "ended"


class TimingMethod(StrEnum):
    UNSPECIFIED = "unspecified"
    REAL_TIME = "real_time"
    GAME_TIME = "game_time"


class BridgeErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    INVALID_ARGUMENT = "invalid_argument"
    OPERATION_FAILED = "operation_failed"
    INTERNAL_ERROR = "internal_error"
    PERMISSION_DENIED = "permission_denied"


class QueryMethod(StrEnum):
    GET_TIMER_STATE = "get_timer_state"
    GET_RUN = "get_run"
    GET_RUN_ICONS = "get_run_icons"
    GET_ATTEMPT = "get_attempt"
    GET_CONTEXT_STATE = "get_context_state"
    GET_COMPLETED_COUNT = "get_completed_count"


class TimerOperation(StrEnum):
    START = "start"
    SPLIT = "split"
    SKIP = "skip"
    UNDO = "undo"
    RESET = "reset"
    PAUSE = "pause"
    RESUME = "resume"


class GameTimeOperation(StrEnum):
    INITIALIZE = "initialize"
    SET = "set"
    PAUSE = "pause"
    RESUME = "resume"


class EventType(StrEnum):
    TIMER_STARTED = "timer_started"
    TIMER_SPLIT = "timer_split"
    TIMER_SKIPPED = "timer_skipped"
    TIMER_UNDO = "timer_undo"
    TIMER_RESET = "timer_reset"
    TIMER_PHASE_CHANGED = "timer_phase_changed"
    RUN_CHANGED = "run_changed"
    CONTEXT_CHANGED = "context_changed"


class TimerState(_Model):
    phase: TimerPhase = Field(strict=False)
    split_index: Int32
    real_time_ticks: Ticks
    game_time_ticks: Ticks | None
    is_game_time_initialized: bool
    is_game_time_paused: bool


class TimeValue(_Model):
    real_time_ticks: Ticks | None
    game_time_ticks: Ticks | None


class AttemptSegment(_Model):
    index: UInt32
    split_time: TimeValue
    custom_variables: dict[str, str]


class AttemptState(_Model):
    attempt_count: UInt32
    segments: list[AttemptSegment]


class CompletedCount(_Model):
    completed_count: UInt32


class ContextState(_Model):
    current_timing_method: TimingMethod = Field(strict=False)
    current_comparison: str
    custom_variables: dict[str, str]


class ComparisonTime(_Model):
    name: str
    time: TimeValue


class SegmentInfo(_Model):
    index: UInt32
    name: str
    comparisons: list[ComparisonTime]
    best_segment_time: TimeValue


class RunMetadata(_Model):
    run_id: str | None
    platform_name: str | None
    region_name: str | None
    uses_emulator: bool
    variables: dict[str, str]


class RunState(_Model):
    game_name: str
    category_name: str
    offset_ticks: Ticks
    file_path: str | None
    layout_path: str | None
    metadata: RunMetadata | None
    comparisons: list[str]
    segments: list[SegmentInfo]


def _decode_icon(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if not isinstance(value, str):
        raise ValueError("An icon must be a Base64 string")
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("An icon must contain valid Base64") from error


_Icon = Annotated[
    bytes,
    BeforeValidator(_decode_icon),
    PlainSerializer(lambda value: base64.b64encode(value).decode("ascii"), return_type=str),
    WithJsonSchema({"type": "string"}),
]


class RunIcons(_Model):
    """Decoded PNG bytes; segment positions, including absent icons, are preserved."""

    game_icon: _Icon | None
    segment_icons: list[_Icon | None]


class BridgeError(_Model):
    code: BridgeErrorCode = Field(strict=False)
    message: str


class BridgeEvent(_Model):
    session_id: NonZeroUInt32
    event_sequence: NonZeroUInt32
    type: EventType = Field(strict=False)
    timer_state: TimerState | None

    @model_validator(mode="after")
    def check_timer_state(self) -> Self:
        if self.type in (EventType.RUN_CHANGED, EventType.CONTEXT_CHANGED):
            if self.timer_state is not None:
                raise ValueError("Changed events require timer_state: null")
        elif self.type != EventType.TIMER_RESET and self.timer_state is None:
            raise ValueError("Timer events require a non-null timer_state")
        return self


class QueryRequest(_Model):
    request_id: UInt32
    method: QueryMethod = Field(strict=False)


class TimerParams(_Model):
    operation: TimerOperation = Field(strict=False)


class TimerRequest(_Model):
    request_id: UInt32
    method: Literal["timer_operation"]
    params: TimerParams


class GameControlParams(_Model):
    operation: Literal["initialize", "pause", "resume"]


class GameSetParams(_Model):
    operation: Literal["set"]
    ticks: Ticks


class GameTimeRequest(_Model):
    request_id: UInt32
    method: Literal["game_time_operation"]
    params: Annotated[GameControlParams | GameSetParams, Field(discriminator="operation")]


RpcRequest = QueryRequest | TimerRequest | GameTimeRequest
RpcResult = TimerState | RunState | RunIcons | AttemptState | ContextState | CompletedCount | None
_Result = TypeVar("_Result")


class SuccessResponse(_Model, Generic[_Result]):
    request_id: UInt32
    session_id: NonZeroUInt32
    result: _Result


class ErrorResponse(_Model):
    request_id: UInt32
    session_id: NonZeroUInt32
    error: BridgeError


RpcResponse = SuccessResponse[RpcResult] | ErrorResponse
