from livesplit.bridge.v3 import common_pb2 as _common_pb2
from livesplit.bridge.v3 import run_pb2 as _run_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Request(_message.Message):
    __slots__ = ("protocol_version", "request_id", "get_timer_state", "get_attempt", "get_run", "get_context_state", "get_completed_count", "timer_operation", "game_time_operation")
    PROTOCOL_VERSION_FIELD_NUMBER: _ClassVar[int]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    GET_TIMER_STATE_FIELD_NUMBER: _ClassVar[int]
    GET_ATTEMPT_FIELD_NUMBER: _ClassVar[int]
    GET_RUN_FIELD_NUMBER: _ClassVar[int]
    GET_CONTEXT_STATE_FIELD_NUMBER: _ClassVar[int]
    GET_COMPLETED_COUNT_FIELD_NUMBER: _ClassVar[int]
    TIMER_OPERATION_FIELD_NUMBER: _ClassVar[int]
    GAME_TIME_OPERATION_FIELD_NUMBER: _ClassVar[int]
    protocol_version: int
    request_id: int
    get_timer_state: GetTimerStateRequest
    get_attempt: GetAttemptRequest
    get_run: GetRunRequest
    get_context_state: GetContextStateRequest
    get_completed_count: GetCompletedCountRequest
    timer_operation: TimerOperationRequest
    game_time_operation: GameTimeOperationRequest
    def __init__(self, protocol_version: _Optional[int] = ..., request_id: _Optional[int] = ..., get_timer_state: _Optional[_Union[GetTimerStateRequest, _Mapping]] = ..., get_attempt: _Optional[_Union[GetAttemptRequest, _Mapping]] = ..., get_run: _Optional[_Union[GetRunRequest, _Mapping]] = ..., get_context_state: _Optional[_Union[GetContextStateRequest, _Mapping]] = ..., get_completed_count: _Optional[_Union[GetCompletedCountRequest, _Mapping]] = ..., timer_operation: _Optional[_Union[TimerOperationRequest, _Mapping]] = ..., game_time_operation: _Optional[_Union[GameTimeOperationRequest, _Mapping]] = ...) -> None: ...

class Response(_message.Message):
    __slots__ = ("protocol_version", "request_id", "session_id", "error", "get_timer_state", "get_attempt", "get_run", "get_context_state", "get_completed_count", "operation")
    PROTOCOL_VERSION_FIELD_NUMBER: _ClassVar[int]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    GET_TIMER_STATE_FIELD_NUMBER: _ClassVar[int]
    GET_ATTEMPT_FIELD_NUMBER: _ClassVar[int]
    GET_RUN_FIELD_NUMBER: _ClassVar[int]
    GET_CONTEXT_STATE_FIELD_NUMBER: _ClassVar[int]
    GET_COMPLETED_COUNT_FIELD_NUMBER: _ClassVar[int]
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    protocol_version: int
    request_id: int
    session_id: int
    error: _common_pb2.BridgeError
    get_timer_state: GetTimerStateResponse
    get_attempt: GetAttemptResponse
    get_run: GetRunResponse
    get_context_state: GetContextStateResponse
    get_completed_count: GetCompletedCountResponse
    operation: _common_pb2.OperationResponse
    def __init__(self, protocol_version: _Optional[int] = ..., request_id: _Optional[int] = ..., session_id: _Optional[int] = ..., error: _Optional[_Union[_common_pb2.BridgeError, _Mapping]] = ..., get_timer_state: _Optional[_Union[GetTimerStateResponse, _Mapping]] = ..., get_attempt: _Optional[_Union[GetAttemptResponse, _Mapping]] = ..., get_run: _Optional[_Union[GetRunResponse, _Mapping]] = ..., get_context_state: _Optional[_Union[GetContextStateResponse, _Mapping]] = ..., get_completed_count: _Optional[_Union[GetCompletedCountResponse, _Mapping]] = ..., operation: _Optional[_Union[_common_pb2.OperationResponse, _Mapping]] = ...) -> None: ...

class GetTimerStateRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetTimerStateResponse(_message.Message):
    __slots__ = ("timer_state",)
    TIMER_STATE_FIELD_NUMBER: _ClassVar[int]
    timer_state: _common_pb2.TimerState
    def __init__(self, timer_state: _Optional[_Union[_common_pb2.TimerState, _Mapping]] = ...) -> None: ...

class GetAttemptRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetAttemptResponse(_message.Message):
    __slots__ = ("attempt",)
    ATTEMPT_FIELD_NUMBER: _ClassVar[int]
    attempt: _common_pb2.AttemptState
    def __init__(self, attempt: _Optional[_Union[_common_pb2.AttemptState, _Mapping]] = ...) -> None: ...

class GetRunRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetRunResponse(_message.Message):
    __slots__ = ("run",)
    RUN_FIELD_NUMBER: _ClassVar[int]
    run: _run_pb2.RunState
    def __init__(self, run: _Optional[_Union[_run_pb2.RunState, _Mapping]] = ...) -> None: ...

class GetContextStateRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetContextStateResponse(_message.Message):
    __slots__ = ("context_state",)
    CONTEXT_STATE_FIELD_NUMBER: _ClassVar[int]
    context_state: _common_pb2.ContextState
    def __init__(self, context_state: _Optional[_Union[_common_pb2.ContextState, _Mapping]] = ...) -> None: ...

class GetCompletedCountRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetCompletedCountResponse(_message.Message):
    __slots__ = ("completed_count",)
    COMPLETED_COUNT_FIELD_NUMBER: _ClassVar[int]
    completed_count: _common_pb2.CompletedCount
    def __init__(self, completed_count: _Optional[_Union[_common_pb2.CompletedCount, _Mapping]] = ...) -> None: ...

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
