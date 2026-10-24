from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

import websocket

from livesplit_bridge import BridgeEvent, TimerState


class FakeWebSocket:
    def __init__(
        self,
        messages: Iterable[Any] = (),
        *,
        timeout: bool = False,
    ) -> None:
        self.messages = list(messages)
        self.always_timeout = timeout
        self.sent: list[str] = []
        self.recv_timeout: float | None = None
        self.shutdown_called = False
        self.close_called = False

    def send(self, payload: str, opcode: int = websocket.ABNF.OPCODE_TEXT) -> None:
        assert opcode == websocket.ABNF.OPCODE_TEXT
        self.sent.append(payload)

    def recv(self) -> Any:
        if self.messages:
            item = self.messages.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        if self.always_timeout:
            raise websocket.WebSocketTimeoutException("timed out")
        raise websocket.WebSocketConnectionClosedException("closed")

    def recv_data(self, control_frame: bool = False) -> tuple[int, Any]:
        item = self.recv()
        if isinstance(item, tuple):
            return item
        if isinstance(item, str):
            return websocket.ABNF.OPCODE_TEXT, item
        return websocket.ABNF.OPCODE_BINARY, item

    def settimeout(self, value: float | None) -> None:
        self.recv_timeout = value

    def close(self) -> None:
        self.close_called = True

    def shutdown(self) -> None:
        self.shutdown_called = True


class FakeConnections:
    def __init__(self, *results: FakeWebSocket | Exception) -> None:
        self.results = list(results)
        self.endpoints: list[str] = []

    def __call__(self, endpoint: str, **kwargs: Any) -> FakeWebSocket:
        self.endpoints.append(endpoint)
        if not self.results:
            raise IndexError("no more fake websockets")
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def timer(**updates: Any) -> TimerState:
    return TimerState.model_validate(
        {
            "phase": "not_running",
            "split_index": -1,
            "real_time_ticks": 0,
            "game_time_ticks": None,
            "is_game_time_initialized": False,
            "is_game_time_paused": False,
            **updates,
        }
    )


def event(
    sequence: int = 1,
    *,
    session_id: int = 42,
    kind: str = "run_changed",
    state: TimerState | None = None,
) -> BridgeEvent:
    return BridgeEvent.model_validate(
        {"session_id": session_id, "event_sequence": sequence, "type": kind, "timer_state": state}
    )


def query_result(method: str) -> dict[str, Any] | None:
    return {
        "get_timer_state": timer().model_dump(mode="json"),
        "get_run": {
            "game_name": "Game",
            "category_name": "Any%",
            "offset_ticks": -100,
            "file_path": None,
            "layout_path": None,
            "metadata": None,
            "comparisons": ["Personal Best"],
            "segments": [],
        },
        "get_run_icons": {"game_icon": None, "segment_icons": [None, None]},
        "get_attempt": {"attempt_count": 4, "segments": []},
        "get_context_state": {
            "current_timing_method": "real_time",
            "current_comparison": "Personal Best",
            "custom_variables": {},
        },
        "get_completed_count": {"completed_count": 9},
        "timer_operation": None,
        "game_time_operation": None,
    }[method]


def response_scenario(*, session_id: int = 42, **body: Any) -> dict[str, Any]:
    return {"session_id": session_id, **body}


class RequestAwareBridgeSocket(FakeWebSocket):
    """Bridge test double that responds to each JSON request's method."""

    def __init__(
        self,
        session_id: int = 42,
        *,
        scenarios: Mapping[str, dict[str, Any] | Exception | list[Any]] | None = None,
    ) -> None:
        super().__init__()
        self.session_id = session_id
        self.scenarios = dict(scenarios or {})

    def send(self, payload: str, opcode: int = websocket.ABNF.OPCODE_TEXT) -> None:
        super().send(payload, opcode)
        request = json.loads(payload)
        method = request["method"]
        scenario = self.scenarios.get(method)
        if isinstance(scenario, list):
            if not scenario:
                raise AssertionError(f"No response scenario remains for {method}")
            scenario = scenario.pop(0)
        if isinstance(scenario, Exception):
            self.messages.append(scenario)
            return
        response = {"session_id": self.session_id, "result": query_result(method)}
        if scenario is not None:
            response = dict(scenario)
        response["request_id"] = request["request_id"]
        self.messages.append(json.dumps(response))
