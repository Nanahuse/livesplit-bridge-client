from __future__ import annotations

import base64
import json
import os
import queue
import socket
import struct
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import websocket

from livesplit_bridge import (
    BridgeClient,
    BridgeClientError,
    BridgeRecoveryState,
    BridgeRemoteError,
    BridgeRpcClient,
    EventType,
    TimerPhase,
)
from livesplit_bridge import rpc as rpc_module

pytestmark = pytest.mark.integration


@pytest.fixture
def endpoints(request: pytest.FixtureRequest) -> Iterator[tuple[str, str]]:
    executable = os.environ.get("BRIDGE_TEST_HOST")
    if not executable:
        pytest.skip("Run uv run tools/run_integration.py to build the pinned official v4 TestHost")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        [executable, "--port", str(port), *getattr(request, "param", ())],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    lines: queue.Queue[str] = queue.Queue()

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put(line.rstrip())
        lines.put("EOF")

    threading.Thread(target=read_output, daemon=True).start()
    deadline = time.monotonic() + 30
    output: list[str] = []
    try:
        while True:
            line = lines.get(timeout=max(0.01, deadline - time.monotonic()))
            output.append(line)
            if line == "READY":
                break
            if line == "EOF":
                pytest.fail("Official v4 TestHost exited: " + "\n".join(output))
        yield f"ws://127.0.0.1:{port}/bridge/v4/rpc", f"ws://127.0.0.1:{port}/bridge/v4/events"
    except queue.Empty:
        pytest.fail("Official v4 TestHost startup timed out: " + "\n".join(output))
    finally:
        if process.poll() is None:
            assert process.stdin is not None
            try:
                process.stdin.write("\n")
                process.stdin.flush()
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=5)
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                stream.close()


def wait_event(client: BridgeClient, kind: EventType) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        event = client.receive(timeout_ms=100)
        if event is not None and event.type is kind:
            assert event.session_id == client.session_id
            return
    pytest.fail(f"No {kind} event from the official v4 Bridge")


def test_real_v4_queries_controls_and_events(endpoints: tuple[str, str]) -> None:
    with BridgeClient(*endpoints) as client:
        initial = client.synchronize(include_completed_count=True)
        assert initial.timer_state.phase is TimerPhase.NOT_RUNNING
        assert initial.run.game_name == "Bridge Test Game"
        assert [segment.name for segment in initial.run.segments] == ["First", "Second"]
        assert initial.context_state.custom_variables["host_var"] == "host-value"
        assert initial.completed_count is not None
        icons = client.get_run_icons()
        assert icons.game_icon is None
        assert icons.segment_icons == [None, None]
        assert client.start() is None
        wait_event(client, EventType.TIMER_STARTED)
        assert client.get_timer_state().phase is TimerPhase.RUNNING
        client.initialize_game_time()
        client.pause_game_time()
        client.set_game_time_ticks(-123456)
        timer = client.get_timer_state()
        assert timer.is_game_time_initialized and timer.is_game_time_paused
        assert timer.game_time_ticks == -123456
        client.resume_game_time()
        assert not client.get_timer_state().is_game_time_paused
        client.pause()
        wait_event(client, EventType.TIMER_PHASE_CHANGED)
        assert client.get_timer_state().phase is TimerPhase.PAUSED
        client.resume()
        assert client.get_timer_state().phase is TimerPhase.RUNNING
        client.split()
        wait_event(client, EventType.TIMER_SPLIT)
        assert client.get_timer_state().split_index == 1
        assert client.get_attempt().segments[0].split_time.real_time_ticks is not None
        client.undo()
        wait_event(client, EventType.TIMER_UNDO)
        assert client.get_timer_state().split_index == 0
        client.skip()
        wait_event(client, EventType.TIMER_SKIPPED)
        assert client.get_timer_state().split_index == 1
        client.split()
        wait_event(client, EventType.TIMER_SPLIT)
        assert client.get_timer_state().phase is TimerPhase.ENDED
        client.reset()
        wait_event(client, EventType.TIMER_RESET)
        assert client.get_timer_state().phase is TimerPhase.NOT_RUNNING
        assert (
            client.get_completed_count().completed_count
            == initial.completed_count.completed_count + 1
        )
        assert client.recovery_state is BridgeRecoveryState.HEALTHY
        assert client.reconnect().session_id == initial.session_id
        client.start()
        wait_event(client, EventType.TIMER_STARTED)


@pytest.mark.parametrize("endpoints", [("--with-icons",)], indirect=True, ids=["with-icons"])
def test_real_run_icons_over_64kib_and_continued_rpc(
    endpoints: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with BridgeClient(*endpoints) as client:
        initial = client.synchronize()
        assert [segment.name for segment in initial.run.segments] == ["First", "Second"]
        rpc_socket = client.rpc._socket
        assert rpc_socket is not None
        receive = rpc_socket.recv_data
        responses: list[tuple[int, bytes | str]] = []

        def capture_response(*args: Any, **kwargs: Any) -> tuple[int, Any]:
            opcode, payload = receive(*args, **kwargs)
            responses.append((opcode, payload))
            return opcode, payload

        # Observe the actual response consumed by get_run_icons(), including Text message
        # reassembly, rather than estimating its size from decoded image bytes.
        with monkeypatch.context() as capture:
            capture.setattr(rpc_socket, "recv_data", capture_response)
            icons = client.get_run_icons()
        assert len(responses) == 1
        opcode, payload = responses[0]
        assert opcode == websocket.ABNF.OPCODE_TEXT
        wire_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload
        assert len(wire_bytes) > 64 * 1024, f"Response was only {len(wire_bytes)} UTF-8 bytes"
        envelope = json.loads(wire_bytes)
        assert envelope["session_id"] == initial.session_id
        wire_icons = envelope["result"]

        game_png = icons.game_icon
        first_png, second_png = icons.segment_icons
        for png, dimensions in ((game_png, (256, 256)), (first_png, (16, 16))):
            assert isinstance(png, bytes)
            assert png.startswith(b"\x89PNG\r\n\x1a\n")
            assert png[12:16] == b"IHDR"
            assert struct.unpack(">II", png[16:24]) == dimensions
        assert game_png == base64.b64decode(wire_icons["game_icon"], validate=True)
        assert first_png == base64.b64decode(wire_icons["segment_icons"][0], validate=True)
        assert second_png is None
        assert wire_icons["segment_icons"][1] is None

        assert client.get_run() == initial.run
        assert client.start() is None
        wait_event(client, EventType.TIMER_STARTED)
        assert client.get_timer_state().phase is TimerPhase.RUNNING
        assert client.rpc._socket is rpc_socket
        assert rpc_socket.connected
        assert client.session_id == initial.session_id
        assert client.recovery_state is BridgeRecoveryState.HEALTHY


def test_real_transport_recovery_without_control_replay(endpoints: tuple[str, str]) -> None:
    with BridgeClient(*endpoints) as client:
        initial = client.synchronize()
        socket = client.rpc._socket
        assert socket is not None
        socket.shutdown()
        with pytest.raises(BridgeClientError):
            client.start()
        assert client.recovery_state is BridgeRecoveryState.RECONNECT_REQUIRED
        recovered = client.reconnect()
        assert recovered.session_id == initial.session_id
        assert recovered.timer_state.phase is TimerPhase.NOT_RUNNING
        client.start()
        wait_event(client, EventType.TIMER_STARTED)


def test_real_permission_denied_retains_rpc_connection(
    endpoints: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect = rpc_module.websocket.create_connection

    def restricted(endpoint: str, **kwargs: Any) -> Any:
        return connect(endpoint, origin="https://example.com", **kwargs)

    monkeypatch.setattr(rpc_module.websocket, "create_connection", restricted)
    with BridgeRpcClient(endpoints[0]) as rpc:
        assert rpc.get_timer_state().phase is TimerPhase.NOT_RUNNING
        with pytest.raises(BridgeRemoteError) as error:
            rpc.start()
        assert error.value.code == "permission_denied"
        assert not rpc.transport_reset
        assert rpc.get_run().game_name == "Bridge Test Game"


def test_fresh_csharp_output_matches_checked_in_contract_samples() -> None:
    generated = os.environ.get("BRIDGE_CSHARP_CASES")
    if not generated:
        pytest.skip("Run tools/run_integration.py to export current official C# DTO samples")
    expected = Path(__file__).parent / "fixtures/csharp-serialized-cases.json"
    assert json.loads(Path(generated).read_text(encoding="utf-8-sig")) == json.loads(
        expected.read_text(encoding="utf-8-sig")
    )
