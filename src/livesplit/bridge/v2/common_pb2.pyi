from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TimerPhase(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TIMER_PHASE_UNSPECIFIED: _ClassVar[TimerPhase]
    NOT_RUNNING: _ClassVar[TimerPhase]
    STARTING: _ClassVar[TimerPhase]
    RUNNING: _ClassVar[TimerPhase]
    PAUSED: _ClassVar[TimerPhase]
    ENDED: _ClassVar[TimerPhase]

class TimingMethod(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TIMING_METHOD_UNSPECIFIED: _ClassVar[TimingMethod]
    REAL_TIME: _ClassVar[TimingMethod]
    GAME_TIME: _ClassVar[TimingMethod]

class TimerOperationType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TIMER_OPERATION_UNSPECIFIED: _ClassVar[TimerOperationType]
    TIMER_START: _ClassVar[TimerOperationType]
    TIMER_SPLIT: _ClassVar[TimerOperationType]
    TIMER_SKIP: _ClassVar[TimerOperationType]
    TIMER_UNDO: _ClassVar[TimerOperationType]
    TIMER_RESET: _ClassVar[TimerOperationType]
    TIMER_PAUSE: _ClassVar[TimerOperationType]
    TIMER_RESUME: _ClassVar[TimerOperationType]

class GameTimeOperationType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    GAME_TIME_OPERATION_UNSPECIFIED: _ClassVar[GameTimeOperationType]
    INITIALIZE: _ClassVar[GameTimeOperationType]
    SET: _ClassVar[GameTimeOperationType]
    GAME_TIME_PAUSE: _ClassVar[GameTimeOperationType]
    GAME_TIME_RESUME: _ClassVar[GameTimeOperationType]

class BridgeEventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    BRIDGE_EVENT_UNSPECIFIED: _ClassVar[BridgeEventType]
    EVENT_TIMER_STARTED: _ClassVar[BridgeEventType]
    EVENT_TIMER_SPLIT: _ClassVar[BridgeEventType]
    EVENT_TIMER_SKIPPED: _ClassVar[BridgeEventType]
    EVENT_TIMER_UNDO: _ClassVar[BridgeEventType]
    EVENT_TIMER_RESET: _ClassVar[BridgeEventType]
    EVENT_TIMER_PAUSED: _ClassVar[BridgeEventType]
    EVENT_TIMER_RESUMED: _ClassVar[BridgeEventType]
    EVENT_GAME_TIME_INITIALIZED: _ClassVar[BridgeEventType]
    EVENT_GAME_TIME_SET: _ClassVar[BridgeEventType]
    EVENT_GAME_TIME_PAUSED: _ClassVar[BridgeEventType]
    EVENT_GAME_TIME_RESUMED: _ClassVar[BridgeEventType]
    EVENT_RUN_CHANGED: _ClassVar[BridgeEventType]
    EVENT_RUNTIME_CHANGED: _ClassVar[BridgeEventType]
    EVENT_HEARTBEAT: _ClassVar[BridgeEventType]
TIMER_PHASE_UNSPECIFIED: TimerPhase
NOT_RUNNING: TimerPhase
STARTING: TimerPhase
RUNNING: TimerPhase
PAUSED: TimerPhase
ENDED: TimerPhase
TIMING_METHOD_UNSPECIFIED: TimingMethod
REAL_TIME: TimingMethod
GAME_TIME: TimingMethod
TIMER_OPERATION_UNSPECIFIED: TimerOperationType
TIMER_START: TimerOperationType
TIMER_SPLIT: TimerOperationType
TIMER_SKIP: TimerOperationType
TIMER_UNDO: TimerOperationType
TIMER_RESET: TimerOperationType
TIMER_PAUSE: TimerOperationType
TIMER_RESUME: TimerOperationType
GAME_TIME_OPERATION_UNSPECIFIED: GameTimeOperationType
INITIALIZE: GameTimeOperationType
SET: GameTimeOperationType
GAME_TIME_PAUSE: GameTimeOperationType
GAME_TIME_RESUME: GameTimeOperationType
BRIDGE_EVENT_UNSPECIFIED: BridgeEventType
EVENT_TIMER_STARTED: BridgeEventType
EVENT_TIMER_SPLIT: BridgeEventType
EVENT_TIMER_SKIPPED: BridgeEventType
EVENT_TIMER_UNDO: BridgeEventType
EVENT_TIMER_RESET: BridgeEventType
EVENT_TIMER_PAUSED: BridgeEventType
EVENT_TIMER_RESUMED: BridgeEventType
EVENT_GAME_TIME_INITIALIZED: BridgeEventType
EVENT_GAME_TIME_SET: BridgeEventType
EVENT_GAME_TIME_PAUSED: BridgeEventType
EVENT_GAME_TIME_RESUMED: BridgeEventType
EVENT_RUN_CHANGED: BridgeEventType
EVENT_RUNTIME_CHANGED: BridgeEventType
EVENT_HEARTBEAT: BridgeEventType

class TimeValue(_message.Message):
    __slots__ = ("real_time_ticks", "game_time_ticks")
    REAL_TIME_TICKS_FIELD_NUMBER: _ClassVar[int]
    GAME_TIME_TICKS_FIELD_NUMBER: _ClassVar[int]
    real_time_ticks: int
    game_time_ticks: int
    def __init__(self, real_time_ticks: _Optional[int] = ..., game_time_ticks: _Optional[int] = ...) -> None: ...

class TimerState(_message.Message):
    __slots__ = ("session_id", "state_revision", "phase", "split_index", "real_time_ticks", "game_time_ticks", "is_game_time_initialized", "is_game_time_paused", "run_revision", "attempt_revision", "runtime_revision")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    STATE_REVISION_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    SPLIT_INDEX_FIELD_NUMBER: _ClassVar[int]
    REAL_TIME_TICKS_FIELD_NUMBER: _ClassVar[int]
    GAME_TIME_TICKS_FIELD_NUMBER: _ClassVar[int]
    IS_GAME_TIME_INITIALIZED_FIELD_NUMBER: _ClassVar[int]
    IS_GAME_TIME_PAUSED_FIELD_NUMBER: _ClassVar[int]
    RUN_REVISION_FIELD_NUMBER: _ClassVar[int]
    ATTEMPT_REVISION_FIELD_NUMBER: _ClassVar[int]
    RUNTIME_REVISION_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    state_revision: int
    phase: TimerPhase
    split_index: int
    real_time_ticks: int
    game_time_ticks: int
    is_game_time_initialized: bool
    is_game_time_paused: bool
    run_revision: int
    attempt_revision: int
    runtime_revision: int
    def __init__(self, session_id: _Optional[int] = ..., state_revision: _Optional[int] = ..., phase: _Optional[_Union[TimerPhase, str]] = ..., split_index: _Optional[int] = ..., real_time_ticks: _Optional[int] = ..., game_time_ticks: _Optional[int] = ..., is_game_time_initialized: bool = ..., is_game_time_paused: bool = ..., run_revision: _Optional[int] = ..., attempt_revision: _Optional[int] = ..., runtime_revision: _Optional[int] = ...) -> None: ...

class AttemptState(_message.Message):
    __slots__ = ("session_id", "attempt_revision", "attempt_count", "completed_count", "segments")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    ATTEMPT_REVISION_FIELD_NUMBER: _ClassVar[int]
    ATTEMPT_COUNT_FIELD_NUMBER: _ClassVar[int]
    COMPLETED_COUNT_FIELD_NUMBER: _ClassVar[int]
    SEGMENTS_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    attempt_revision: int
    attempt_count: int
    completed_count: int
    segments: _containers.RepeatedCompositeFieldContainer[AttemptSegment]
    def __init__(self, session_id: _Optional[int] = ..., attempt_revision: _Optional[int] = ..., attempt_count: _Optional[int] = ..., completed_count: _Optional[int] = ..., segments: _Optional[_Iterable[_Union[AttemptSegment, _Mapping]]] = ...) -> None: ...

class AttemptSegment(_message.Message):
    __slots__ = ("index", "split_time", "custom_variables")
    class CustomVariablesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    INDEX_FIELD_NUMBER: _ClassVar[int]
    SPLIT_TIME_FIELD_NUMBER: _ClassVar[int]
    CUSTOM_VARIABLES_FIELD_NUMBER: _ClassVar[int]
    index: int
    split_time: TimeValue
    custom_variables: _containers.ScalarMap[str, str]
    def __init__(self, index: _Optional[int] = ..., split_time: _Optional[_Union[TimeValue, _Mapping]] = ..., custom_variables: _Optional[_Mapping[str, str]] = ...) -> None: ...

class RuntimeState(_message.Message):
    __slots__ = ("session_id", "runtime_revision", "current_timing_method", "current_comparison", "global_hotkeys_enabled", "custom_variables")
    class CustomVariablesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    RUNTIME_REVISION_FIELD_NUMBER: _ClassVar[int]
    CURRENT_TIMING_METHOD_FIELD_NUMBER: _ClassVar[int]
    CURRENT_COMPARISON_FIELD_NUMBER: _ClassVar[int]
    GLOBAL_HOTKEYS_ENABLED_FIELD_NUMBER: _ClassVar[int]
    CUSTOM_VARIABLES_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    runtime_revision: int
    current_timing_method: TimingMethod
    current_comparison: str
    global_hotkeys_enabled: bool
    custom_variables: _containers.ScalarMap[str, str]
    def __init__(self, session_id: _Optional[int] = ..., runtime_revision: _Optional[int] = ..., current_timing_method: _Optional[_Union[TimingMethod, str]] = ..., current_comparison: _Optional[str] = ..., global_hotkeys_enabled: bool = ..., custom_variables: _Optional[_Mapping[str, str]] = ...) -> None: ...

class OperationResponse(_message.Message):
    __slots__ = ("success", "message", "timer_state")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    TIMER_STATE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    timer_state: TimerState
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., timer_state: _Optional[_Union[TimerState, _Mapping]] = ...) -> None: ...

class BridgeError(_message.Message):
    __slots__ = ("code", "message")
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    code: int
    message: str
    def __init__(self, code: _Optional[int] = ..., message: _Optional[str] = ...) -> None: ...

class BridgeEvent(_message.Message):
    __slots__ = ("session_id", "event_sequence", "type", "timer_state")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    EVENT_SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    TIMER_STATE_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    event_sequence: int
    type: BridgeEventType
    timer_state: TimerState
    def __init__(self, session_id: _Optional[int] = ..., event_sequence: _Optional[int] = ..., type: _Optional[_Union[BridgeEventType, str]] = ..., timer_state: _Optional[_Union[TimerState, _Mapping]] = ...) -> None: ...
