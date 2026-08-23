from __future__ import annotations

import pytest
import zmq

from livesplit_bridge import (
    BridgeEventSubscriber,
    BridgeTimeoutError,
    common_pb2,
)

from .test_client import FakeContext, FakeSocket


def test_receive_decodes_bridge_event_and_subscribes_to_all_topics() -> None:
    expected = common_pb2.BridgeEvent(
        session_id=9,
        event_sequence=4,
        type=common_pb2.EVENT_TIMER_SPLIT,
    )
    socket = FakeSocket([expected.SerializeToString()])
    subscriber = BridgeEventSubscriber(context=FakeContext(socket), timeout_ms=50)

    actual = subscriber.receive()

    assert actual == expected
    assert (zmq.SUBSCRIBE, b"") in socket.options
    subscriber.close()


def test_event_timeout_is_reported() -> None:
    socket = FakeSocket(poll_result=False)
    subscriber = BridgeEventSubscriber(context=FakeContext(socket), timeout_ms=25)

    with pytest.raises(BridgeTimeoutError, match="25 ms"):
        next(subscriber)

    subscriber.close()


def test_receive_timeout_can_be_overridden() -> None:
    socket = FakeSocket(poll_result=False)
    subscriber = BridgeEventSubscriber(context=FakeContext(socket))

    with pytest.raises(BridgeTimeoutError, match="3 ms"):
        subscriber.receive(timeout_ms=3)

    subscriber.close()
