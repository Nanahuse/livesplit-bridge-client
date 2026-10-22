from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from livesplit_bridge import BridgeEventSubscriber, BridgeProtocolError, BridgeRpcClient, RunIcons
from livesplit_bridge import rpc as rpc_module

from .support import FakeConnections, FakeWebSocket, RequestAwareBridgeSocket

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLES = json.loads((FIXTURES / "csharp-serialized-cases.json").read_text(encoding="utf-8-sig"))


@pytest.mark.parametrize(
    ("request_id", "method", "attribute", "expected"),
    [
        (1, "get_timer_state", "real_time_ticks", 123456),
        (8, "get_run", "game_name", "Example Game"),
        (3, "get_attempt", "attempt_count", 4),
        (4, "get_context_state", "current_comparison", "Personal Best"),
        (5, "get_completed_count", "completed_count", 2),
    ],
)
def test_client_returns_data_from_official_csharp_response(
    monkeypatch: pytest.MonkeyPatch,
    request_id: int,
    method: str,
    attribute: str,
    expected: Any,
) -> None:
    body = next(
        case["data"]
        for case in SAMPLES
        if case["schema"] == "response" and case["data"]["request_id"] == request_id
    )
    socket = FakeWebSocket([json.dumps(body)])
    monkeypatch.setattr(rpc_module.websocket, "create_connection", FakeConnections(socket))
    with BridgeRpcClient() as client:
        client._next_request_id = request_id
        result = getattr(client, method)()
        assert getattr(result, attribute) == expected
        assert client.session_id == body["session_id"]
        assert not client.transport_reset


@pytest.mark.parametrize(
    "body",
    [
        case["data"]
        for case in SAMPLES
        if case["schema"] == "event"
        and (
            case["data"]["type"] in ("timer_started", "run_changed")
            or (case["data"]["type"] == "timer_reset" and case["data"]["timer_state"] is None)
        )
    ],
    ids=lambda body: body["type"],
)
def test_subscriber_exposes_official_csharp_event(
    monkeypatch: pytest.MonkeyPatch,
    body: dict[str, Any],
) -> None:
    monkeypatch.setattr(
        rpc_module.websocket,
        "create_connection",
        FakeConnections(FakeWebSocket([json.dumps(body)])),
    )
    with BridgeEventSubscriber() as subscriber:
        event = subscriber.receive()
    assert event is not None
    assert event.type == body["type"]
    assert event.session_id == body["session_id"]
    assert event.event_sequence == body["event_sequence"]
    if body["timer_state"] is None:
        assert event.timer_state is None
    else:
        assert event.timer_state is not None
        assert event.timer_state.real_time_ticks == body["timer_state"]["real_time_ticks"]


@pytest.mark.parametrize(
    "payload",
    [
        {"game_icon": "not Base64!", "segment_icons": []},
        {"game_icon": None, "segment_icons": ["%%%%"]},
        {"game_icon": None, "segment_icons": ["é"]},
    ],
    ids=["game-icon", "segment-icon", "non-ascii-base64"],
)
def test_invalid_base64_discards_rpc_connection(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
) -> None:
    socket = RequestAwareBridgeSocket(
        scenarios={"get_run_icons": {"session_id": 42, "result": payload}}
    )
    monkeypatch.setattr(rpc_module.websocket, "create_connection", FakeConnections(socket))
    with BridgeRpcClient() as client, pytest.raises(BridgeProtocolError):
        client.get_run_icons()
    assert socket.shutdown_called
    assert client.transport_reset
    assert client.session_id == 0


def test_icon_bytes_nulls_and_segment_order(monkeypatch: pytest.MonkeyPatch) -> None:
    # Exercise the client's Base64 conversion with a PNG emitted by the official C# DTO.
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
