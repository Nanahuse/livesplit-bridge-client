from livesplit.bridge.v2 import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RunState(_message.Message):
    __slots__ = ("session_id", "run_revision", "game_name", "category_name", "offset_ticks", "file_path", "layout_path", "metadata", "comparisons", "segments", "game_icon")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    RUN_REVISION_FIELD_NUMBER: _ClassVar[int]
    GAME_NAME_FIELD_NUMBER: _ClassVar[int]
    CATEGORY_NAME_FIELD_NUMBER: _ClassVar[int]
    OFFSET_TICKS_FIELD_NUMBER: _ClassVar[int]
    FILE_PATH_FIELD_NUMBER: _ClassVar[int]
    LAYOUT_PATH_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    COMPARISONS_FIELD_NUMBER: _ClassVar[int]
    SEGMENTS_FIELD_NUMBER: _ClassVar[int]
    GAME_ICON_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    run_revision: int
    game_name: str
    category_name: str
    offset_ticks: int
    file_path: str
    layout_path: str
    metadata: RunMetadata
    comparisons: _containers.RepeatedScalarFieldContainer[str]
    segments: _containers.RepeatedCompositeFieldContainer[SegmentInfo]
    game_icon: Image
    def __init__(self, session_id: _Optional[int] = ..., run_revision: _Optional[int] = ..., game_name: _Optional[str] = ..., category_name: _Optional[str] = ..., offset_ticks: _Optional[int] = ..., file_path: _Optional[str] = ..., layout_path: _Optional[str] = ..., metadata: _Optional[_Union[RunMetadata, _Mapping]] = ..., comparisons: _Optional[_Iterable[str]] = ..., segments: _Optional[_Iterable[_Union[SegmentInfo, _Mapping]]] = ..., game_icon: _Optional[_Union[Image, _Mapping]] = ...) -> None: ...

class SegmentInfo(_message.Message):
    __slots__ = ("index", "name", "comparisons", "best_segment_time", "icon")
    INDEX_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    COMPARISONS_FIELD_NUMBER: _ClassVar[int]
    BEST_SEGMENT_TIME_FIELD_NUMBER: _ClassVar[int]
    ICON_FIELD_NUMBER: _ClassVar[int]
    index: int
    name: str
    comparisons: _containers.RepeatedCompositeFieldContainer[ComparisonTime]
    best_segment_time: _common_pb2.TimeValue
    icon: Image
    def __init__(self, index: _Optional[int] = ..., name: _Optional[str] = ..., comparisons: _Optional[_Iterable[_Union[ComparisonTime, _Mapping]]] = ..., best_segment_time: _Optional[_Union[_common_pb2.TimeValue, _Mapping]] = ..., icon: _Optional[_Union[Image, _Mapping]] = ...) -> None: ...

class ComparisonTime(_message.Message):
    __slots__ = ("name", "time")
    NAME_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    name: str
    time: _common_pb2.TimeValue
    def __init__(self, name: _Optional[str] = ..., time: _Optional[_Union[_common_pb2.TimeValue, _Mapping]] = ...) -> None: ...

class RunMetadata(_message.Message):
    __slots__ = ("run_id", "platform_name", "region_name", "uses_emulator", "variables")
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
    run_id: str
    platform_name: str
    region_name: str
    uses_emulator: bool
    variables: _containers.ScalarMap[str, str]
    def __init__(self, run_id: _Optional[str] = ..., platform_name: _Optional[str] = ..., region_name: _Optional[str] = ..., uses_emulator: bool = ..., variables: _Optional[_Mapping[str, str]] = ...) -> None: ...

class Image(_message.Message):
    __slots__ = ("mime_type", "data", "width", "height")
    MIME_TYPE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    mime_type: str
    data: bytes
    width: int
    height: int
    def __init__(self, mime_type: _Optional[str] = ..., data: _Optional[bytes] = ..., width: _Optional[int] = ..., height: _Optional[int] = ...) -> None: ...
