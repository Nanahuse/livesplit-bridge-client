from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RunSnapshot(_message.Message):
    __slots__ = ("session_id", "run_revision", "captured_state_revision", "game_name", "category_name", "offset_ticks", "file_path", "layout_path", "metadata", "comparisons", "segments", "attempt_count")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    RUN_REVISION_FIELD_NUMBER: _ClassVar[int]
    CAPTURED_STATE_REVISION_FIELD_NUMBER: _ClassVar[int]
    GAME_NAME_FIELD_NUMBER: _ClassVar[int]
    CATEGORY_NAME_FIELD_NUMBER: _ClassVar[int]
    OFFSET_TICKS_FIELD_NUMBER: _ClassVar[int]
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    LAYOUT_PATH_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    COMPARISONS_FIELD_NUMBER: _ClassVar[int]
    SEGMENTS_FIELD_NUMBER: _ClassVar[int]
    ATTEMPT_COUNT_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    run_revision: int
    captured_state_revision: int
    game_name: str
    category_name: str
    offset_ticks: int
    file_path: str
    layout_path: str
    metadata: RunMetadata
    comparisons: _containers.RepeatedScalarFieldContainer[str]
    segments: _containers.RepeatedCompositeFieldContainer[SegmentInfo]
    attempt_count: int
    def __init__(self, session_id: _Optional[int] = ..., run_revision: _Optional[int] = ..., captured_state_revision: _Optional[int] = ..., game_name: _Optional[str] = ..., category_name: _Optional[str] = ..., offset_ticks: _Optional[int] = ..., file_path: _Optional[str] = ..., layout_path: _Optional[str] = ..., metadata: _Optional[_Union[RunMetadata, _Mapping]] = ..., comparisons: _Optional[_Iterable[str]] = ..., segments: _Optional[_Iterable[_Union[SegmentInfo, _Mapping]]] = ..., attempt_count: _Optional[int] = ...) -> None: ...

class SegmentInfo(_message.Message):
    __slots__ = ("index", "name", "comparisons", "best_segment_time", "custom_variables")
    class CustomVariablesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    INDEX_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    COMPARISONS_FIELD_NUMBER: _ClassVar[int]
    BEST_SEGMENT_TIME_FIELD_NUMBER: _ClassVar[int]
    CUSTOM_VARIABLES_FIELD_NUMBER: _ClassVar[int]
    index: int
    name: str
    comparisons: _containers.RepeatedCompositeFieldContainer[ComparisonTime]
    best_segment_time: TimeValue
    custom_variables: _containers.ScalarMap[str, str]
    def __init__(self, index: _Optional[int] = ..., name: _Optional[str] = ..., comparisons: _Optional[_Iterable[_Union[ComparisonTime, _Mapping]]] = ..., best_segment_time: _Optional[_Union[TimeValue, _Mapping]] = ..., custom_variables: _Optional[_Mapping[str, str]] = ...) -> None: ...

class TimeValue(_message.Message):
    __slots__ = ("real_time_ticks", "game_time_ticks")
    REAL_TIME_TICKS_FIELD_NUMBER: _ClassVar[int]
    GAME_TIME_TICKS_FIELD_NUMBER: _ClassVar[int]
    real_time_ticks: int
    game_time_ticks: int
    def __init__(self, real_time_ticks: _Optional[int] = ..., game_time_ticks: _Optional[int] = ...) -> None: ...

class ComparisonTime(_message.Message):
    __slots__ = ("name", "time")
    NAME_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    name: str
    time: TimeValue
    def __init__(self, name: _Optional[str] = ..., time: _Optional[_Union[TimeValue, _Mapping]] = ...) -> None: ...

class RunMetadata(_message.Message):
    __slots__ = ("run_id", "platform_name", "region_name", "uses_emulator", "variables", "custom_variables")
    class VariablesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_NAME_FIELD_NUMBER: _ClassVar[int]
    REGION_NAME_FIELD_NUMBER: _ClassVar[int]
    USES_EMULATOR_FIELD_NUMBER: _ClassVar[int]
    VARIABLES_FIELD_NUMBER: _ClassVar[int]
    CUSTOM_VARIABLES_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    platform_name: str
    region_name: str
    uses_emulator: bool
    variables: _containers.ScalarMap[str, str]
    custom_variables: _containers.RepeatedCompositeFieldContainer[CustomVariable]
    def __init__(self, run_id: _Optional[str] = ..., platform_name: _Optional[str] = ..., region_name: _Optional[str] = ..., uses_emulator: bool = ..., variables: _Optional[_Mapping[str, str]] = ..., custom_variables: _Optional[_Iterable[_Union[CustomVariable, _Mapping]]] = ...) -> None: ...

class CustomVariable(_message.Message):
    __slots__ = ("name", "value", "is_permanent")
    NAME_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    IS_PERMANENT_FIELD_NUMBER: _ClassVar[int]
    name: str
    value: str
    is_permanent: bool
    def __init__(self, name: _Optional[str] = ..., value: _Optional[str] = ..., is_permanent: bool = ...) -> None: ...
