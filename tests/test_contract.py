from __future__ import annotations

import base64
import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import TypeAdapter, ValidationError

from livesplit_bridge import BridgeEvent, RpcRequest, RpcResponse, RunIcons, TimerState
from livesplit_bridge import rpc as rpc_module

from .support import FakeConnections, RequestAwareBridgeSocket, timer

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
ADAPTERS = {
    "request": TypeAdapter(RpcRequest),
    "response": TypeAdapter(RpcResponse),
    "event": TypeAdapter(BridgeEvent),
}
VALIDATORS = {
    kind: Draft202012Validator(json.loads((ROOT / "schemas" / "v4" / name).read_text()))
    for kind, name in {
        "request": "rpc-request.schema.json",
        "response": "rpc-response.schema.json",
        "event": "bridge-event.schema.json",
    }.items()
}
SAMPLES = json.loads((FIXTURES / "csharp-serialized-cases.json").read_text(encoding="utf-8-sig"))
INVALID = json.loads((FIXTURES / "validation-cases.json").read_text(encoding="utf-8-sig"))


def accepts(kind: str, data: Any) -> bool:
    try:
        ADAPTERS[kind].validate_json(json.dumps(data))
    except ValidationError:
        return False
    return True


@pytest.mark.parametrize("case", SAMPLES + INVALID, ids=lambda case: case["name"])
def test_official_csharp_messages_and_invalid_cases(case: dict[str, Any]) -> None:
    assert VALIDATORS[case["schema"]].is_valid(case["data"]) is case["valid"]
    assert accepts(case["schema"], case["data"]) is case["valid"]
    if case["valid"]:
        model = ADAPTERS[case["schema"]].validate_json(json.dumps(case["data"]))
        # In particular, decoded icon bytes serialize back to their original Base64 strings.
        assert json.loads(model.model_dump_json()) == case["data"]


def mutations(value: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key in value:
            missing = dict(value)
            del missing[key]
            yield f"missing {key}", missing
            for label, replacement in mutations(value[key]):
                yield f"{key}/{label}", {**value, key: replacement}
        yield "extra property", {**value, "unexpected": True}
    elif isinstance(value, list):
        for index, item in enumerate(value):
            for label, replacement in mutations(item):
                changed = list(value)
                changed[index] = replacement
                yield f"{index}/{label}", changed
    candidates = [
        None,
        True,
        False,
        [],
        {},
        -1,
        0,
        1,
        2**32 - 1,
        2**32,
        -(2**31) - 1,
        2**31,
        -(2**63),
        -(2**63) - 1,
        2**63 - 1,
        2**63,
        "unknown",
    ]
    for replacement in candidates:
        # Identity of JSON types matters, e.g. bool is not an integer on the wire.
        if type(value) is not type(replacement) or value != replacement:
            yield repr(replacement), replacement


@pytest.mark.parametrize("case", SAMPLES, ids=lambda case: case["name"])
def test_nested_contract_constraints_match_official_schema(case: dict[str, Any]) -> None:
    for label, data in mutations(copy.deepcopy(case["data"])):
        # The official schema only says string; runtime also validates Base64 encoding.
        if ("game_icon" in label or "segment_icons" in label) and "'unknown'" in label:
            continue
        assert accepts(case["schema"], data) == VALIDATORS[case["schema"]].is_valid(data), label


@pytest.mark.parametrize("field", ["real_time_ticks", "game_time_ticks", "split_index"])
@pytest.mark.parametrize("value", [True, "1", 1.0])
def test_integer_fields_never_coerce(field: str, value: Any) -> None:
    body = timer().model_dump(mode="json")
    body[field] = value
    with pytest.raises(ValidationError):
        TimerState.model_validate_json(json.dumps(body))


@pytest.mark.parametrize(
    "payload",
    [
        {"game_icon": "not Base64!", "segment_icons": []},
        {"game_icon": None, "segment_icons": ["%%%%"]},
        {"game_icon": None, "segment_icons": ["é"]},
        {"game_icon": None, "segment_icons": None},
        {"game_icon": 12, "segment_icons": []},
    ],
)
def test_bad_icons_become_protocol_errors(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    from livesplit_bridge import BridgeProtocolError, BridgeRpcClient

    socket = RequestAwareBridgeSocket(
        scenarios={"get_run_icons": {"session_id": 42, "result": payload}}
    )
    monkeypatch.setattr(rpc_module.websocket, "create_connection", FakeConnections(socket))
    with BridgeRpcClient() as client, pytest.raises(BridgeProtocolError):
        client.get_run_icons()
    assert socket.shutdown_called


def test_icon_bytes_nulls_and_segment_order(monkeypatch: pytest.MonkeyPatch) -> None:
    from livesplit_bridge import BridgeRpcClient

    # A C# serialized real PNG, including the PNG signature.
    png_case = next(
        case
        for case in SAMPLES
        if case["schema"] == "response"
        and isinstance(case["data"].get("result"), dict)
        and case["data"]["result"].get("game_icon")
    )
    png = png_case["data"]["result"]["game_icon"]
    payload = {"game_icon": png, "segment_icons": [None, png, None]}
    socket = RequestAwareBridgeSocket(
        scenarios={"get_run_icons": {"session_id": 42, "result": payload}}
    )
    monkeypatch.setattr(rpc_module.websocket, "create_connection", FakeConnections(socket))
    with BridgeRpcClient() as client:
        icons = client.get_run_icons()
    assert isinstance(icons, RunIcons)
    assert icons.game_icon == base64.b64decode(png)
    assert icons.game_icon.startswith(b"\x89PNG\r\n\x1a\n")
    assert icons.segment_icons == [None, icons.game_icon, None]
