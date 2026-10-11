from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import websocket

from livesplit_bridge import bridge_pb2, common_pb2, run_pb2


class FakeWebSocket:
    def __init__(
        self,
        messages: Iterable[Any] = (),
        *,
        timeout: bool = False,
    ) -> None:
        self.messages = list(messages)
        self.always_timeout = timeout
        self.sent: list[bytes] = []
        self.recv_timeout: float | None = None
        self.shutdown_called = False
        self.close_called = False

    def send_binary(self, payload: bytes) -> None:
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


def response_scenario(*, session_id: int = 42, **body: Any) -> bridge_pb2.Response:
    return bridge_pb2.Response(protocol_version=3, session_id=session_id, **body)


class RequestAwareBridgeSocket(FakeWebSocket):
    """Small Bridge test double that responds based on each request body."""

    def __init__(
        self,
        session_id: int = 42,
        *,
        scenarios: Mapping[str, bridge_pb2.Response | Exception | list[Any]] | None = None,
        completed_count: int = 9,
    ) -> None:
        super().__init__()
        self.session_id = session_id
        self.completed_count = completed_count
        self.scenarios = dict(scenarios or {})

    def send_binary(self, payload: bytes) -> None:
        super().send_binary(payload)
        request = bridge_pb2.Request.FromString(payload)
        body = request.WhichOneof("body")
        scenario = self.scenarios.get(body)
        if isinstance(scenario, list):
            if not scenario:
                raise AssertionError(f"No response scenario remains for {body}")
            scenario = scenario.pop(0)
        if isinstance(scenario, Exception):
            self.messages.append(scenario)
            return

        response = bridge_pb2.Response(
            protocol_version=3,
            request_id=request.request_id,
            session_id=self.session_id,
        )
        if isinstance(scenario, bridge_pb2.Response):
            response.CopyFrom(scenario)
            response.protocol_version = 3
            response.request_id = request.request_id
        elif scenario is not None:
            raise TypeError(f"Unsupported response scenario for {body}: {type(scenario)!r}")
        elif body == "get_timer_state":
            response.get_timer_state.timer_state.phase = common_pb2.NOT_RUNNING
        elif body == "get_attempt":
            response.get_attempt.attempt.attempt_count = 4
        elif body == "get_run":
            response.get_run.run.CopyFrom(run_pb2.RunState(game_name="Game"))
        elif body == "get_context_state":
            response.get_context_state.context_state.current_comparison = "Personal Best"
        elif body == "get_completed_count":
            response.get_completed_count.completed_count.completed_count = self.completed_count
        elif body in ("timer_operation", "game_time_operation"):
            response.operation.SetInParent()
        else:
            raise AssertionError(f"Unexpected Bridge request: {body}")
        self.messages.append(response.SerializeToString())
