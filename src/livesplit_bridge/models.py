"""Stable public names and client conveniences over generated JSON wire models.

No wire fields, enum values, or numeric constraints are defined here. Those are
owned by the pinned C# DTOs and generated into _generated/protocol.py.
"""

from __future__ import annotations

import base64
import binascii
from typing import Generic, Self, TypeVar, cast

from pydantic import RootModel, model_validator

from ._generated import protocol as _wire
from ._generated.protocol import (
    AttemptSegment as AttemptSegment,
)
from ._generated.protocol import (
    AttemptState as AttemptState,
)
from ._generated.protocol import (
    BridgeError as BridgeError,
)
from ._generated.protocol import (
    BridgeErrorCode as BridgeErrorCode,
)
from ._generated.protocol import (
    ComparisonTime as ComparisonTime,
)
from ._generated.protocol import (
    CompletedCount as CompletedCount,
)
from ._generated.protocol import (
    ContextState as ContextState,
)
from ._generated.protocol import (
    ErrorResponse as ErrorResponse,
)
from ._generated.protocol import (
    EventType as EventType,
)
from ._generated.protocol import (
    GameControlParams as GameControlParams,
)
from ._generated.protocol import (
    GameSetParams as GameSetParams,
)
from ._generated.protocol import (
    GameTimeOperation as GameTimeOperation,
)
from ._generated.protocol import (
    QueryMethod as QueryMethod,
)
from ._generated.protocol import (
    QueryRequest as QueryRequest,
)
from ._generated.protocol import (
    RunMetadata as RunMetadata,
)
from ._generated.protocol import (
    RunState as RunState,
)
from ._generated.protocol import (
    SegmentInfo as SegmentInfo,
)
from ._generated.protocol import (
    TimerOperation as TimerOperation,
)
from ._generated.protocol import (
    TimerParams as TimerParams,
)
from ._generated.protocol import (
    TimerPhase as TimerPhase,
)
from ._generated.protocol import (
    TimerRequest as TimerRequest,
)
from ._generated.protocol import (
    TimerState as TimerState,
)
from ._generated.protocol import (
    TimeValue as TimeValue,
)
from ._generated.protocol import (
    TimingMethod as TimingMethod,
)

# Counter arithmetic belongs to the transport; field constraints are generated.
UINT32_MAX = 2**32 - 1
_Root = TypeVar("_Root")
_UNSET = object()


class _View(RootModel[_Root]):
    """Accept the existing flat keyword constructor while validation stays generated."""

    def __init__(self, root: object = _UNSET, **fields: object) -> None:
        if root is _UNSET:
            root = fields
        elif fields:
            raise ValueError("Pass either a root value or keyword fields")
        self.__pydantic_validator__.validate_python(root, self_instance=self)


def _decode_icon(value: str | None) -> bytes | None:
    if value is None:
        return None
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("An icon must contain valid Base64") from error


class RunIcons(_View[_wire.RunIcons]):
    """Expose decoded PNG bytes without changing the generated wire contract."""

    @model_validator(mode="before")
    @classmethod
    def encode_input_bytes(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        def encode(icon: object) -> object:
            return base64.b64encode(icon).decode("ascii") if isinstance(icon, bytes) else icon

        data = dict(value)
        if "game_icon" in data:
            data["game_icon"] = encode(data["game_icon"])
        if isinstance(data.get("segment_icons"), list):
            data["segment_icons"] = [encode(icon) for icon in data["segment_icons"]]
        return data

    @model_validator(mode="after")
    def validate_base64(self) -> Self:
        _decode_icon(self.root.game_icon)
        for icon in self.root.segment_icons:
            _decode_icon(icon)
        return self

    @property
    def game_icon(self) -> bytes | None:
        return _decode_icon(self.root.game_icon)

    @property
    def segment_icons(self) -> list[bytes | None]:
        return [_decode_icon(icon) for icon in self.root.segment_icons]


class BridgeEvent(_View[_wire.BridgeEvent]):
    """Keep flat Event access while the generated model owns the oneOf branches."""

    @property
    def session_id(self) -> int:
        return self.root.root.session_id

    @property
    def event_sequence(self) -> int:
        return self.root.root.event_sequence

    @property
    def type(self) -> EventType:
        return EventType(self.root.root.type)

    @property
    def timer_state(self) -> TimerState | None:
        return self.root.root.timer_state


class GameTimeRequest(_View[_wire.GameTimeRequest]):
    @property
    def request_id(self) -> int:
        return self.root.root.request_id

    @property
    def method(self) -> str:
        return self.root.root.method

    @property
    def params(self) -> GameControlParams | GameSetParams:
        return self.root.root.params


RpcRequest = QueryRequest | TimerRequest | GameTimeRequest
RpcResult = TimerState | RunState | RunIcons | AttemptState | ContextState | CompletedCount | None
_Result = TypeVar("_Result")


class SuccessResponse(_View[_wire.SuccessResponse], Generic[_Result]):
    @model_validator(mode="after")
    def validate_icons(self) -> Self:
        value = self.root.root.result
        if isinstance(value, _wire.RunIcons):
            RunIcons.model_validate(value)
        return self

    @property
    def request_id(self) -> int:
        return self.root.root.request_id

    @property
    def session_id(self) -> int:
        return self.root.root.session_id

    @property
    def result(self) -> _Result:
        value = self.root.root.result
        if isinstance(value, _wire.RunIcons):
            return cast(_Result, RunIcons.model_validate(value))
        return cast(_Result, value)


RpcResponse = SuccessResponse[RpcResult] | ErrorResponse
