from __future__ import annotations

import pytest
import websocket

from livesplit_bridge import (
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


def test_receive_decodes_bridge_event(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = common_pb2.BridgeEvent(
        session_id=9,
        event_sequence=4,
        type=common_pb2.EVENT_TIMER_SPLIT,
    )
    socket = FakeWebSocket([expected.SerializeToString()])
    install(monkeypatch, socket)
    subscriber = BridgeEventSubscriber(receive_timeout_ms=50)

    actual = subscriber.receive()

    assert actual == expected
    assert socket.recv_timeout == 0.05
    subscriber.close()


def test_receive_decodes_heartbeat_without_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = common_pb2.BridgeEvent(
        session_id=9,
        event_sequence=4,
        type=common_pb2.EVENT_HEARTBEAT,
    )
    install(monkeypatch, FakeWebSocket([expected.SerializeToString()]))
    subscriber = BridgeEventSubscriber(receive_timeout_ms=50)

    actual = subscriber.receive()

    assert actual is not None
    assert actual.type == common_pb2.EVENT_HEARTBEAT
    assert actual.event_sequence == expected.event_sequence
    assert not actual.HasField("snapshot")
    subscriber.close()


def test_iterator_yields_events(monkeypatch: pytest.MonkeyPatch) -> None:
    first = common_pb2.BridgeEvent(
        session_id=9, event_sequence=1, type=common_pb2.EVENT_STATE_SNAPSHOT
    )
    second = common_pb2.BridgeEvent(
        session_id=9, event_sequence=2, type=common_pb2.EVENT_TIMER_SPLIT
    )
    socket = FakeWebSocket([first.SerializeToString(), second.SerializeToString()])
    install(monkeypatch, socket)
    subscriber = BridgeEventSubscriber(receive_timeout_ms=25)

    assert iter(subscriber) is subscriber
    assert next(subscriber) == first
    assert next(subscriber) == second
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


def test_text_frame_is_rejected_as_protocol_error(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeWebSocket(["not binary"]))
    subscriber = BridgeEventSubscriber(receive_timeout_ms=25)

    with pytest.raises(BridgeProtocolError, match="text frame"):
        subscriber.receive()

    subscriber.close()


def test_malformed_protobuf_is_rejected_as_protocol_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(monkeypatch, FakeWebSocket([b"\x08"]))
    subscriber = BridgeEventSubscriber(receive_timeout_ms=25)

    with pytest.raises(BridgeProtocolError, match="malformed"):
        subscriber.receive()

    subscriber.close()


def test_websocket_close_is_connection_lost(monkeypatch: pytest.MonkeyPatch) -> None:
    install(
        monkeypatch,
        FakeWebSocket([websocket.WebSocketConnectionClosedException("closed")]),
    )
    subscriber = BridgeEventSubscriber(receive_timeout_ms=25)

    with pytest.raises(BridgeConnectionLostError):
        subscriber.receive()

    subscriber.close()


def test_connection_reset_is_connection_lost(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeWebSocket([ConnectionResetError("reset by peer")]))
    subscriber = BridgeEventSubscriber(receive_timeout_ms=25)

    with pytest.raises(BridgeConnectionLostError):
        subscriber.receive()

    subscriber.close()


class FakeMonotonic:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def state_event(
    session_id: int = 9,
    event_sequence: int = 1,
    type: common_pb2.BridgeEventType = common_pb2.EVENT_STATE_SNAPSHOT,
) -> common_pb2.BridgeEvent:
    return common_pb2.BridgeEvent(
        session_id=session_id,
        event_sequence=event_sequence,
        type=type,
    )


def test_heartbeat_expiry_is_not_extended_by_state_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    first = state_event()
    install(monkeypatch, FakeWebSocket([first.SerializeToString()]))
    subscriber = BridgeEventSubscriber(heartbeat_timeout_ms=100)

    assert subscriber.receive() == first

    clock.now = 0.15
    with pytest.raises(BridgeConnectionLostError, match="100 ms"):
        subscriber.receive()

    subscriber.close()


def test_heartbeat_extends_the_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    heartbeat = common_pb2.BridgeEvent(
        session_id=9, event_sequence=0, type=common_pb2.EVENT_HEARTBEAT
    )
    last = state_event(event_sequence=3)
    socket = FakeWebSocket(
        [
            heartbeat.SerializeToString(),
            heartbeat.SerializeToString(),
            last.SerializeToString(),
        ]
    )
    install(monkeypatch, socket)
    subscriber = BridgeEventSubscriber(heartbeat_timeout_ms=100)

    subscriber.receive()
    clock.now = 0.08
    subscriber.receive()
    clock.now = 0.15

    assert subscriber.receive() == last

    subscriber.close()


def test_heartbeat_deadline_precedes_one_shot_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    install(monkeypatch, FakeWebSocket(timeout=True))
    subscriber = BridgeEventSubscriber(heartbeat_timeout_ms=50)

    with pytest.raises(BridgeConnectionLostError, match="50 ms"):
        subscriber.receive(timeout_ms=100)

    subscriber.close()


def test_one_shot_timeout_precedes_heartbeat_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    install(monkeypatch, FakeWebSocket(timeout=True))
    subscriber = BridgeEventSubscriber(heartbeat_timeout_ms=100)

    assert subscriber.receive(timeout_ms=50) is None

    subscriber.close()


@pytest.mark.parametrize(
    "event_type",
    [common_pb2.EVENT_STATE_SNAPSHOT, common_pb2.EVENT_HEARTBEAT],
)
def test_heartbeat_deadline_expiry_after_receive(
    monkeypatch: pytest.MonkeyPatch,
    event_type: common_pb2.BridgeEventType,
) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    event = state_event(type=event_type)
    socket = FakeWebSocket(
        [event.SerializeToString()],
        on_recv=lambda: setattr(clock, "now", 0.15),
    )
    install(monkeypatch, socket)
    subscriber = BridgeEventSubscriber(heartbeat_timeout_ms=100)

    with pytest.raises(BridgeConnectionLostError, match="100 ms"):
        subscriber.receive()

    subscriber.close()


def test_heartbeat_deadline_starts_at_subscriber_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    event = state_event()
    install(monkeypatch, FakeWebSocket([event.SerializeToString()]))
    subscriber = BridgeEventSubscriber(heartbeat_timeout_ms=100)

    clock.now = 10.0

    with pytest.raises(BridgeConnectionLostError, match="100 ms"):
        subscriber.receive()

    subscriber.close()


def test_same_subscriber_stays_expired_after_heartbeat_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    first = state_event()
    heartbeat = common_pb2.BridgeEvent(type=common_pb2.EVENT_HEARTBEAT)
    socket = FakeWebSocket([first.SerializeToString(), heartbeat.SerializeToString()])
    install(monkeypatch, socket)
    subscriber = BridgeEventSubscriber(heartbeat_timeout_ms=100)

    assert subscriber.receive() == first

    clock.now = 0.15
    with pytest.raises(BridgeConnectionLostError):
        subscriber.receive()

    with pytest.raises(BridgeConnectionLostError):
        subscriber.receive()

    subscriber.close()


def test_new_subscriber_resumes_heartbeat_monitoring_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    first = state_event()
    install(monkeypatch, FakeWebSocket([first.SerializeToString()]))
    expired = BridgeEventSubscriber(heartbeat_timeout_ms=100)

    assert expired.receive() == first

    clock.now = 0.15
    with pytest.raises(BridgeConnectionLostError):
        expired.receive()
    expired.close()

    heartbeat = common_pb2.BridgeEvent(type=common_pb2.EVENT_HEARTBEAT)
    install(monkeypatch, FakeWebSocket([heartbeat.SerializeToString()]))
    resumed = BridgeEventSubscriber(heartbeat_timeout_ms=100)

    clock.now = 0.18
    assert resumed.receive() == heartbeat

    resumed.close()


def test_heartbeat_expiry_remains_a_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    install(monkeypatch, FakeWebSocket(timeout=True))
    subscriber = BridgeEventSubscriber(heartbeat_timeout_ms=100)

    clock.now = 0.15
    with pytest.raises(BridgeConnectionLostError):
        subscriber.receive()

    subscriber.close()


def test_receive_timeout_is_not_a_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeWebSocket(timeout=True))
    subscriber = BridgeEventSubscriber(receive_timeout_ms=25)

    assert subscriber.receive() is None
    subscriber.close()


def test_heartbeat_none_preserves_receive_timeout_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(monkeypatch, FakeWebSocket(timeout=True))
    subscriber = BridgeEventSubscriber(receive_timeout_ms=25, heartbeat_timeout_ms=None)

    assert subscriber.receive() is None

    subscriber.close()


def test_negative_heartbeat_timeout_is_rejected() -> None:
    with pytest.raises(ValueError, match="heartbeat_timeout_ms"):
        BridgeEventSubscriber(heartbeat_timeout_ms=-1)


def test_negative_receive_timeout_is_rejected() -> None:
    with pytest.raises(ValueError, match="receive_timeout_ms"):
        BridgeEventSubscriber(receive_timeout_ms=-1)


@pytest.mark.parametrize(
    "failure",
    [
        OSError("connection refused"),
        websocket.WebSocketException("handshake failed"),
    ],
)
def test_connect_failure_is_wrapped_as_client_error(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    install(monkeypatch, failure)

    with pytest.raises(BridgeClientError, match="event") as error:
        BridgeEventSubscriber()

    assert "ws://127.0.0.1:54000/bridge/v1/events" in str(error.value)
