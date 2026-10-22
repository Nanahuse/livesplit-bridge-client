from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter

from livesplit_bridge import (
    BridgeEventSubscriber,
    BridgeProtocolError,
    BridgeRemoteError,
    BridgeRpcClient,
    RpcRequest,
    RunIcons,
)
from livesplit_bridge import rpc as rpc_module

from .support import FakeConnections, FakeWebSocket, RequestAwareBridgeSocket, timer

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLES = json.loads((FIXTURES / "csharp-serialized-cases.json").read_text(encoding="utf-8-sig"))
INVALID = json.loads((FIXTURES / "validation-cases.json").read_text(encoding="utf-8-sig"))


def query_method(result: dict[str, Any]) -> str:
    for field, method in (
        ("phase", "get_timer_state"),
        ("game_name", "get_run"),
        ("game_icon", "get_run_icons"),
        ("attempt_count", "get_attempt"),
        ("current_comparison", "get_context_state"),
        ("completed_count", "get_completed_count"),
    ):
        if field in result:
            return method
    raise AssertionError(f"Unexpected official C# result: {result}")


@pytest.mark.parametrize(
    "case", [c for c in SAMPLES if c["schema"] == "response"], ids=lambda case: case["name"]
)
def test_client_receives_official_csharp_response(
    monkeypatch: pytest.MonkeyPatch, case: dict[str, Any]
) -> None:
    body = case["data"]
    socket = FakeWebSocket([json.dumps(body)])
    monkeypatch.setattr(rpc_module.websocket, "create_connection", FakeConnections(socket))
    with BridgeRpcClient() as client:
        client._next_request_id = body["request_id"]
        if "error" in body:
            with pytest.raises(BridgeRemoteError) as error:
                client.start()
            assert error.value.code == body["error"]["code"]
            assert error.value.message == body["error"]["message"]
        elif body["result"] is None:
            assert client.start() is None
        else:
            result = getattr(client, query_method(body["result"]))()
            assert isinstance(result, BaseModel)
            assert result.model_dump(mode="json") == body["result"]
        assert client.session_id == body["session_id"]
        assert not client.transport_reset


@pytest.mark.parametrize(
    "case", [c for c in SAMPLES if c["schema"] == "event"], ids=lambda case: case["name"]
)
def test_subscriber_receives_official_csharp_event(
    monkeypatch: pytest.MonkeyPatch, case: dict[str, Any]
) -> None:
    monkeypatch.setattr(
        rpc_module.websocket,
        "create_connection",
        FakeConnections(FakeWebSocket([json.dumps(case["data"])])),
    )
    with BridgeEventSubscriber() as subscriber:
        event = subscriber.receive()
    assert event is not None
    assert event.model_dump(mode="json") == case["data"]
    assert event.type == case["data"]["type"]
    assert event.session_id == case["data"]["session_id"]
    assert event.event_sequence == case["data"]["event_sequence"]


@pytest.mark.parametrize(
    "case", [c for c in SAMPLES if c["schema"] == "request"], ids=lambda case: case["name"]
)
def test_client_serializes_request_with_official_csharp_shape(
    monkeypatch: pytest.MonkeyPatch, case: dict[str, Any]
) -> None:
    socket = RequestAwareBridgeSocket()
    monkeypatch.setattr(rpc_module.websocket, "create_connection", FakeConnections(socket))
    request = TypeAdapter(RpcRequest).validate_python(case["data"])
    with BridgeRpcClient() as client:
        client._next_request_id = case["data"]["request_id"]
        client.request(request)
    assert json.loads(socket.sent[0]) == case["data"]


@pytest.mark.parametrize(
    "case",
    [c for c in INVALID if c["schema"] in ("response", "event")],
    ids=lambda case: case["name"],
)
def test_client_rejects_official_malformed_messages(
    monkeypatch: pytest.MonkeyPatch, case: dict[str, Any]
) -> None:
    socket = FakeWebSocket([json.dumps(case["data"])])
    monkeypatch.setattr(rpc_module.websocket, "create_connection", FakeConnections(socket))
    if case["schema"] == "event":
        with BridgeEventSubscriber() as subscriber, pytest.raises(BridgeProtocolError):
            subscriber.receive()
    else:
        with BridgeRpcClient() as client, pytest.raises(BridgeProtocolError):
            client._next_request_id = case["data"]["request_id"]
            # Icon-specific invalid cases must reach the icon query's result validation.
            body = case["data"].get("result")
            method = query_method(body) if isinstance(body, dict) else "get_timer_state"
            getattr(client, method)()
        assert socket.shutdown_called


@pytest.mark.parametrize("field", list(timer().model_dump()))
def test_client_rejects_missing_required_timer_fields(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    result = timer().model_dump(mode="json")
    del result[field]
    socket = RequestAwareBridgeSocket(
        scenarios={"get_timer_state": {"session_id": 42, "result": result}}
    )
    monkeypatch.setattr(rpc_module.websocket, "create_connection", FakeConnections(socket))
    with BridgeRpcClient() as client, pytest.raises(BridgeProtocolError):
        client.get_timer_state()
    assert client.session_id == 0
    assert socket.shutdown_called


@pytest.mark.parametrize("field", ["real_time_ticks", "game_time_ticks", "split_index"])
@pytest.mark.parametrize("value", [True, "1", 1.0, 2**63, -(2**63) - 1])
def test_client_rejects_coercion_and_out_of_range_times(
    monkeypatch: pytest.MonkeyPatch, field: str, value: Any
) -> None:
    body = timer().model_dump(mode="json")
    body[field] = value
    socket = RequestAwareBridgeSocket(
        scenarios={"get_timer_state": {"session_id": 42, "result": body}}
    )
    monkeypatch.setattr(rpc_module.websocket, "create_connection", FakeConnections(socket))
    with BridgeRpcClient() as client, pytest.raises(BridgeProtocolError):
        client.get_timer_state()
    assert socket.shutdown_called


@pytest.mark.parametrize(
    ("result_key", "path", "value"),
    [
        ("game_name", ("segments", 0, "index"), -1),
        ("game_name", ("segments", 0, "index"), 2**32),
        ("game_name", ("offset_ticks",), 2**63),
        ("game_name", ("segments", 0, "best_segment_time", "real_time_ticks"), True),
        ("game_name", ("segments", 0, "comparisons", 0, "time", "game_time_ticks"), 2**63),
        ("game_name", ("metadata", "uses_emulator"), "false"),
        ("game_name", ("metadata", "variables"), {"key": 1}),
        ("attempt_count", ("attempt_count",), 2**32),
        ("attempt_count", ("segments", 0, "split_time", "game_time_ticks"), "1"),
        ("current_comparison", ("custom_variables",), {"key": False}),
        ("current_comparison", ("current_timing_method",), "invalid"),
        ("completed_count", ("completed_count",), -1),
        ("phase", ("split_index",), 2**31),
        ("phase", ("split_index",), -(2**31) - 1),
        ("phase", ("is_game_time_paused",), 0),
        ("phase", ("phase",), "invalid"),
        ("phase", ("unexpected",), 1),
    ],
)
def test_client_rejects_invalid_nested_query_data(
    monkeypatch: pytest.MonkeyPatch, result_key: str, path: tuple[str | int, ...], value: Any
) -> None:
    case = next(
        c
        for c in SAMPLES
        if c["schema"] == "response"
        and isinstance(c["data"].get("result"), dict)
        and result_key in c["data"]["result"]
        and (result_key != "game_name" or c["data"]["result"]["metadata"] is not None)
    )
    body = copy.deepcopy(case["data"]["result"])
    target = body
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    method = query_method(body)
    socket = RequestAwareBridgeSocket(scenarios={method: {"session_id": 42, "result": body}})
    monkeypatch.setattr(rpc_module.websocket, "create_connection", FakeConnections(socket))
    with BridgeRpcClient() as client, pytest.raises(BridgeProtocolError):
        getattr(client, method)()
    assert socket.shutdown_called


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
