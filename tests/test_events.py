from __future__ import annotations

from typing import cast

import pytest
import websocket

from livesplit_bridge import (
    DEFAULT_EVENT_ENDPOINT,
    BridgeClientError,
    BridgeConnectionLostError,
    BridgeEventSubscriber,
    BridgeProtocolError,
    common_pb2,
)
from livesplit_bridge import events as events_module

from .test_rpc import FakeConnections, FakeWebSocket


def install(
    monkeypatch: pytest.MonkeyPatch, *results: FakeWebSocket | Exception
) -> FakeConnections:
    connections = FakeConnections(*results)
    monkeypatch.setattr(events_module.websocket, "create_connection", connections)
    return connections


def test_default_endpoint_is_v3() -> None:
    assert DEFAULT_EVENT_ENDPOINT == "ws://127.0.0.1:54000/bridge/v3/events"


def test_receive_decodes_timer_event_with_callback_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = common_pb2.BridgeEvent(
        session_id=9,
        event_sequence=4,
        type=common_pb2.EVENT_TIMER_SPLIT,
        timer_state=common_pb2.TimerState(phase=common_pb2.ENDED, split_index=3),
    )
    socket = FakeWebSocket([expected.SerializeToString()])
    connections = install(monkeypatch, socket)
    subscriber = BridgeEventSubscriber(receive_timeout_ms=50)

    assert subscriber.receive() == expected
    assert socket.recv_timeout == 0.05
    assert connections.endpoints == [DEFAULT_EVENT_ENDPOINT]
    subscriber.close()


@pytest.mark.parametrize(
    "event_type",
    [common_pb2.EVENT_RUN_CHANGED, common_pb2.EVENT_CONTEXT_CHANGED],
)
def test_run_and_context_events_have_no_timer_state(
    monkeypatch: pytest.MonkeyPatch,
    event_type: common_pb2.BridgeEventType,
) -> None:
    expected = common_pb2.BridgeEvent(
        session_id=9,
        event_sequence=5,
        type=event_type,
    )
    install(monkeypatch, FakeWebSocket([expected.SerializeToString()]))
    subscriber = BridgeEventSubscriber()

    actual = subscriber.receive()

    assert actual == expected
    assert actual is not None
    assert not actual.HasField("timer_state")
    subscriber.close()


def test_event_sequence_and_session_are_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        common_pb2.BridgeEvent(
            session_id=12,
            event_sequence=sequence,
            type=common_pb2.EVENT_TIMER_PHASE_CHANGED,
            timer_state=common_pb2.TimerState(phase=common_pb2.PAUSED),
        )
        for sequence in (1, 2)
    ]
    install(monkeypatch, FakeWebSocket([event.SerializeToString() for event in events]))
    subscriber = BridgeEventSubscriber(receive_timeout_ms=25)

    assert [subscriber.receive(), subscriber.receive()] == events
    subscriber.close()


def test_low_level_subscriber_preserves_unknown_event_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unknown = common_pb2.BridgeEvent(
        session_id=12,
        event_sequence=57,
        type=cast(common_pb2.BridgeEventType, 999),
    )
    install(monkeypatch, FakeWebSocket([unknown.SerializeToString()]))
    subscriber = BridgeEventSubscriber()

    assert subscriber.receive() == unknown
    subscriber.close()


def test_configured_receive_timeout_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = FakeWebSocket(timeout=True)
    install(monkeypatch, socket)
    subscriber = BridgeEventSubscriber(receive_timeout_ms=25)

    assert subscriber.receive() is None

    subscriber.close()


def test_receive_timeout_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = FakeWebSocket(timeout=True)
    install(monkeypatch, socket)
    subscriber = BridgeEventSubscriber()

    assert subscriber.receive(timeout_ms=3) is None
    assert socket.recv_timeout == 0.003
    subscriber.close()


@pytest.mark.parametrize(
    "payload",
    ["not binary", b"\x08"],
    ids=["text-frame", "malformed-protobuf"],
)
def test_invalid_event_payload_is_protocol_error(
    monkeypatch: pytest.MonkeyPatch,
    payload: str | bytes,
) -> None:
    install(monkeypatch, FakeWebSocket([payload]))
    subscriber = BridgeEventSubscriber(receive_timeout_ms=25)

    with pytest.raises(BridgeProtocolError):
        subscriber.receive()

    subscriber.close()


def test_websocket_close_is_connection_lost(monkeypatch: pytest.MonkeyPatch) -> None:
    install(
        monkeypatch,
        FakeWebSocket([websocket.WebSocketConnectionClosedException("closed")]),
    )
    subscriber = BridgeEventSubscriber(receive_timeout_ms=25)

    with pytest.raises(BridgeConnectionLostError, match="closed"):
        subscriber.receive()

    subscriber.close()


def test_connection_reset_is_connection_lost(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeWebSocket([ConnectionResetError("reset by peer")]))
    subscriber = BridgeEventSubscriber(receive_timeout_ms=25)

    with pytest.raises(BridgeConnectionLostError, match="closed"):
        subscriber.receive()

    subscriber.close()


def test_connect_failure_is_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, websocket.WebSocketException("handshake failed"))

    with pytest.raises(BridgeClientError, match="event") as error:
        BridgeEventSubscriber()

    assert DEFAULT_EVENT_ENDPOINT in str(error.value)


def test_negative_receive_timeout_is_rejected() -> None:
    with pytest.raises(ValueError, match="receive_timeout_ms"):
        BridgeEventSubscriber(receive_timeout_ms=-1)


def test_negative_per_call_timeout_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeWebSocket())
    subscriber = BridgeEventSubscriber()

    with pytest.raises(ValueError, match="timeout_ms"):
        subscriber.receive(timeout_ms=-1)

    subscriber.close()
