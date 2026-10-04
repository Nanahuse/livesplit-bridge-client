from livesplit.bridge.v2 import common_pb2 as _common_pb2
from livesplit.bridge.v2 import run_pb2 as _run_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Request(_message.Message):
    __slots__ = ("protocol_version", "request_id", "attach", "get_timer_state", "timer_operation", "game_time_operation", "get_run", "get_attempt", "get_runtime_state")
    PROTOCOL_VERSION_FIELD_NUMBER: _ClassVar[int]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    ATTACH_FIELD_NUMBER: _ClassVar[int]
    GET_TIMER_STATE_FIELD_NUMBER: _ClassVar[int]
    TIMER_OPERATION_FIELD_NUMBER: _ClassVar[int]
    GAME_TIME_OPERATION_FIELD_NUMBER: _ClassVar[int]
    GET_RUN_FIELD_NUMBER: _ClassVar[int]
    GET_ATTEMPT_FIELD_NUMBER: _ClassVar[int]
    GET_RUNTIME_STATE_FIELD_NUMBER: _ClassVar[int]
    protocol_version: int
    request_id: int
    attach: AttachRequest
    get_timer_state: GetTimerStateRequest
    timer_operation: TimerOperationRequest
    game_time_operation: GameTimeOperationRequest
    get_run: GetRunRequest
    get_attempt: GetAttemptRequest
    get_runtime_state: GetRuntimeStateRequest
    def __init__(self, protocol_version: _Optional[int] = ..., request_id: _Optional[int] = ..., attach: _Optional[_Union[AttachRequest, _Mapping]] = ..., get_timer_state: _Optional[_Union[GetTimerStateRequest, _Mapping]] = ..., timer_operation: _Optional[_Union[TimerOperationRequest, _Mapping]] = ..., game_time_operation: _Optional[_Union[GameTimeOperationRequest, _Mapping]] = ..., get_run: _Optional[_Union[GetRunRequest, _Mapping]] = ..., get_attempt: _Optional[_Union[GetAttemptRequest, _Mapping]] = ..., get_runtime_state: _Optional[_Union[GetRuntimeStateRequest, _Mapping]] = ...) -> None: ...

class Response(_message.Message):
    __slots__ = ("protocol_version", "request_id", "error", "attach", "get_timer_state", "operation", "get_run", "get_attempt", "get_runtime_state")
    PROTOCOL_VERSION_FIELD_NUMBER: _ClassVar[int]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    ATTACH_FIELD_NUMBER: _ClassVar[int]
    GET_TIMER_STATE_FIELD_NUMBER: _ClassVar[int]
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    GET_RUN_FIELD_NUMBER: _ClassVar[int]
    GET_ATTEMPT_FIELD_NUMBER: _ClassVar[int]
    GET_RUNTIME_STATE_FIELD_NUMBER: _ClassVar[int]
    protocol_version: int
    request_id: int
    error: _common_pb2.BridgeError
    attach: AttachResponse
    get_timer_state: GetTimerStateResponse
    operation: _common_pb2.OperationResponse
    get_run: GetRunResponse
    get_attempt: GetAttemptResponse
    get_runtime_state: GetRuntimeStateResponse
    def __init__(self, protocol_version: _Optional[int] = ..., request_id: _Optional[int] = ..., error: _Optional[_Union[_common_pb2.BridgeError, _Mapping]] = ..., attach: _Optional[_Union[AttachResponse, _Mapping]] = ..., get_timer_state: _Optional[_Union[GetTimerStateResponse, _Mapping]] = ..., operation: _Optional[_Union[_common_pb2.OperationResponse, _Mapping]] = ..., get_run: _Optional[_Union[GetRunResponse, _Mapping]] = ..., get_attempt: _Optional[_Union[GetAttemptResponse, _Mapping]] = ..., get_runtime_state: _Optional[_Union[GetRuntimeStateResponse, _Mapping]] = ...) -> None: ...

class AttachRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AttachResponse(_message.Message):
    __slots__ = ("session_id", "timer_state")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    TIMER_STATE_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    timer_state: _common_pb2.TimerState
    def __init__(self, session_id: _Optional[int] = ..., timer_state: _Optional[_Union[_common_pb2.TimerState, _Mapping]] = ...) -> None: ...

class GetTimerStateRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetTimerStateResponse(_message.Message):
    __slots__ = ("timer_state",)
    TIMER_STATE_FIELD_NUMBER: _ClassVar[int]
    timer_state: _common_pb2.TimerState
    def __init__(self, timer_state: _Optional[_Union[_common_pb2.TimerState, _Mapping]] = ...) -> None: ...

class GetRunRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetRunResponse(_message.Message):
    __slots__ = ("run",)
    RUN_FIELD_NUMBER: _ClassVar[int]
    run: _run_pb2.RunState
    def __init__(self, run: _Optional[_Union[_run_pb2.RunState, _Mapping]] = ...) -> None: ...

class GetAttemptRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetAttemptResponse(_message.Message):
    __slots__ = ("attempt",)
    ATTEMPT_FIELD_NUMBER: _ClassVar[int]
    attempt: _common_pb2.AttemptState
    def __init__(self, attempt: _Optional[_Union[_common_pb2.AttemptState, _Mapping]] = ...) -> None: ...

class GetRuntimeStateRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetRuntimeStateResponse(_message.Message):
    __slots__ = ("runtime_state",)
    RUNTIME_STATE_FIELD_NUMBER: _ClassVar[int]
    runtime_state: _common_pb2.RuntimeState
    def __init__(self, runtime_state: _Optional[_Union[_common_pb2.RuntimeState, _Mapping]] = ...) -> None: ...

class TimerOperationRequest(_message.Message):
    __slots__ = ("operation",)
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    operation: _common_pb2.TimerOperationType
    def __init__(self, operation: _Optional[_Union[_common_pb2.TimerOperationType, str]] = ...) -> None: ...

class GameTimeOperationRequest(_message.Message):
    __slots__ = ("operation", "ticks")
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    TICKS_FIELD_NUMBER: _ClassVar[int]
    operation: _common_pb2.GameTimeOperationType
    ticks: int
    def __init__(self, operation: _Optional[_Union[_common_pb2.GameTimeOperationType, str]] = ..., ticks: _Optional[int] = ...) -> None: ...
