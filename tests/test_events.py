from __future__ import annotations

import pytest
import zmq

from livesplit_bridge import (
    BridgeEventStreamLostError,
    BridgeEventSubscriber,
    BridgeTimeoutError,
    common_pb2,
)
from livesplit_bridge import events as events_module

from .test_client import FakeContext, FakeSocket


def test_receive_decodes_bridge_event_and_subscribes_to_all_topics() -> None:
    expected = common_pb2.BridgeEvent(
        session_id=9,
        event_sequence=4,
        type=common_pb2.EVENT_TIMER_SPLIT,
    )
    socket = FakeSocket([expected.SerializeToString()])
    subscriber = BridgeEventSubscriber(context=FakeContext(socket), receive_timeout_ms=50)

    actual = subscriber.receive()

    assert actual == expected
    assert (zmq.SUBSCRIBE, b"") in socket.options
    subscriber.close()


def test_receive_decodes_heartbeat_without_snapshot() -> None:
    expected = common_pb2.BridgeEvent(
        session_id=9,
        event_sequence=4,
        type=common_pb2.EVENT_HEARTBEAT,
    )
    socket = FakeSocket([expected.SerializeToString()])
    subscriber = BridgeEventSubscriber(context=FakeContext(socket), receive_timeout_ms=50)

    actual = subscriber.receive()

    assert actual.type == common_pb2.EVENT_HEARTBEAT
    assert actual.event_sequence == expected.event_sequence
    assert not actual.HasField("snapshot")
    subscriber.close()


def test_event_timeout_is_reported() -> None:
    socket = FakeSocket(poll_result=False)
    subscriber = BridgeEventSubscriber(context=FakeContext(socket), receive_timeout_ms=25)

    with pytest.raises(BridgeTimeoutError, match="25 ms"):
        next(subscriber)

    subscriber.close()


def test_receive_timeout_can_be_overridden() -> None:
    socket = FakeSocket(poll_result=False)
    subscriber = BridgeEventSubscriber(context=FakeContext(socket))

    with pytest.raises(BridgeTimeoutError, match="3 ms"):
        subscriber.receive(timeout_ms=3)

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


def test_heartbeat_expiry_is_not_extended_by_state_events(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    first = state_event()
    socket = FakeSocket([first.SerializeToString()])
    subscriber = BridgeEventSubscriber(context=FakeContext(socket), heartbeat_timeout_ms=100)

    assert subscriber.receive() == first

    clock.now = 0.15
    with pytest.raises(BridgeEventStreamLostError, match="100 ms"):
        subscriber.receive()

    subscriber.close()


def test_heartbeat_extends_the_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    heartbeat = common_pb2.BridgeEvent(
        session_id=9, event_sequence=0, type=common_pb2.EVENT_HEARTBEAT
    )
    last = state_event(event_sequence=3)
    socket = FakeSocket(
        [
            heartbeat.SerializeToString(),
            heartbeat.SerializeToString(),
            last.SerializeToString(),
        ]
    )
    subscriber = BridgeEventSubscriber(context=FakeContext(socket), heartbeat_timeout_ms=100)

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
    socket = FakeSocket(poll_result=False)
    subscriber = BridgeEventSubscriber(context=FakeContext(socket), heartbeat_timeout_ms=50)

    with pytest.raises(BridgeEventStreamLostError, match="50 ms"):
        subscriber.receive(timeout_ms=100)

    subscriber.close()


def test_one_shot_timeout_precedes_heartbeat_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    socket = FakeSocket(poll_result=False)
    subscriber = BridgeEventSubscriber(context=FakeContext(socket), heartbeat_timeout_ms=100)

    with pytest.raises(BridgeTimeoutError, match="50 ms"):
        subscriber.receive(timeout_ms=50)

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

    class DeadlineCrossingSocket(FakeSocket):
        def poll(self, timeout: int, flags: int) -> bool:
            assert flags == zmq.POLLIN
            clock.now = 0.15
            return True

    socket = DeadlineCrossingSocket([event.SerializeToString()])
    subscriber = BridgeEventSubscriber(context=FakeContext(socket), heartbeat_timeout_ms=100)

    with pytest.raises(BridgeEventStreamLostError, match="100 ms"):
        subscriber.receive()

    subscriber.close()


def test_heartbeat_deadline_starts_at_subscriber_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    event = state_event()
    socket = FakeSocket([event.SerializeToString()])
    subscriber = BridgeEventSubscriber(context=FakeContext(socket), heartbeat_timeout_ms=100)

    clock.now = 10.0

    with pytest.raises(BridgeEventStreamLostError, match="100 ms"):
        subscriber.receive()

    subscriber.close()


def test_same_subscriber_stays_expired_after_heartbeat_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    first = state_event()
    heartbeat = common_pb2.BridgeEvent(type=common_pb2.EVENT_HEARTBEAT)
    socket = FakeSocket([first.SerializeToString(), heartbeat.SerializeToString()])
    subscriber = BridgeEventSubscriber(context=FakeContext(socket), heartbeat_timeout_ms=100)

    assert subscriber.receive() == first

    clock.now = 0.15
    with pytest.raises(BridgeEventStreamLostError):
        subscriber.receive()

    with pytest.raises(BridgeEventStreamLostError):
        subscriber.receive()

    subscriber.close()


def test_new_subscriber_resumes_heartbeat_monitoring_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    first = state_event()
    socket = FakeSocket([first.SerializeToString()])
    expired = BridgeEventSubscriber(context=FakeContext(socket), heartbeat_timeout_ms=100)

    assert expired.receive() == first

    clock.now = 0.15
    with pytest.raises(BridgeEventStreamLostError):
        expired.receive()
    expired.close()

    heartbeat = common_pb2.BridgeEvent(type=common_pb2.EVENT_HEARTBEAT)
    socket = FakeSocket([heartbeat.SerializeToString()])
    resumed = BridgeEventSubscriber(context=FakeContext(socket), heartbeat_timeout_ms=100)

    clock.now = 0.18
    assert resumed.receive() == heartbeat

    resumed.close()


def test_negative_heartbeat_timeout_is_rejected() -> None:
    socket = FakeSocket()

    with pytest.raises(ValueError, match="heartbeat_timeout_ms"):
        BridgeEventSubscriber(context=FakeContext(socket), heartbeat_timeout_ms=-1)

    socket.close()


def test_negative_receive_timeout_is_rejected() -> None:
    socket = FakeSocket()

    with pytest.raises(ValueError, match="receive_timeout_ms"):
        BridgeEventSubscriber(context=FakeContext(socket), receive_timeout_ms=-1)

    socket.close()


def test_event_stream_lost_is_not_caught_as_event_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    socket = FakeSocket(poll_result=False)
    subscriber = BridgeEventSubscriber(context=FakeContext(socket), heartbeat_timeout_ms=100)

    clock.now = 0.15
    with pytest.raises(BridgeEventStreamLostError):
        subscriber.receive()

    assert not issubclass(BridgeEventStreamLostError, BridgeTimeoutError)
    subscriber.close()


def test_event_timeout_is_not_caught_as_event_stream_lost() -> None:
    socket = FakeSocket(poll_result=False)
    subscriber = BridgeEventSubscriber(context=FakeContext(socket), receive_timeout_ms=25)

    with pytest.raises(BridgeTimeoutError):
        subscriber.receive()

    assert not issubclass(BridgeTimeoutError, BridgeEventStreamLostError)
    subscriber.close()


def test_heartbeat_none_preserves_receive_timeout_behavior() -> None:
    socket = FakeSocket(poll_result=False)
    subscriber = BridgeEventSubscriber(
        context=FakeContext(socket), receive_timeout_ms=25, heartbeat_timeout_ms=None
    )

    with pytest.raises(BridgeTimeoutError, match="25 ms"):
        next(subscriber)

    subscriber.close()
