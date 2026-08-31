from __future__ import annotations

from typing import Any

import pytest
import zmq

from livesplit_bridge import (
    BridgeClient,
    BridgeClientError,
    BridgeEventStreamLostError,
    BridgeRemoteError,
    BridgeTimeoutError,
    bridge_pb2,
    common_pb2,
)
from livesplit_bridge import client as client_module
from livesplit_bridge import events as events_module

from .test_rpc import FakeContext, FakeSocket, encoded_response


def _snapshot_response(request_id: int, snapshot: common_pb2.TimerSnapshot) -> bytes:
    return encoded_response(
        request_id,
        get_snapshot=bridge_pb2.GetSnapshotResponse(snapshot=snapshot),
    )


def test_single_shared_context_creates_subscriber_before_client() -> None:
    sub_socket = FakeSocket()
    req_socket = FakeSocket()
    context = FakeContext(sub_socket, req_socket)

    client = BridgeClient(context=context)

    assert context.socket_types == [zmq.SUB, zmq.REQ]
    assert (zmq.SUBSCRIBE, b"") in sub_socket.options
    assert req_socket.endpoint == client.rpc.rpc_endpoint
    client.close()


def test_rpc_operations_delegate_to_client() -> None:
    expected = common_pb2.TimerSnapshot(session_id=42, split_index=3)
    sub_socket = FakeSocket()
    req_socket = FakeSocket(
        [
            _snapshot_response(1, expected),
            encoded_response(2, operation=common_pb2.OperationResponse(success=True)),
        ]
    )
    client = BridgeClient(context=FakeContext(sub_socket, req_socket))

    assert client.snapshot() == expected
    assert client.start().success

    request = bridge_pb2.Request.FromString(req_socket.sent[1])
    assert request.timer_operation.operation == common_pb2.TIMER_START
    client.close()


def test_receive_and_iteration_use_current_subscriber() -> None:
    first = common_pb2.BridgeEvent(
        session_id=9, event_sequence=1, type=common_pb2.EVENT_STATE_SNAPSHOT
    )
    second = common_pb2.BridgeEvent(
        session_id=9, event_sequence=2, type=common_pb2.EVENT_TIMER_SPLIT
    )
    sub_socket = FakeSocket([first.SerializeToString(), second.SerializeToString()])
    client = BridgeClient(context=FakeContext(sub_socket, FakeSocket()))

    assert client.receive() == first
    assert iter(client) is client
    assert next(client) == second
    client.close()


def test_receive_timeout_is_forwarded() -> None:
    sub_socket = FakeSocket(poll_result=False)
    client = BridgeClient(context=FakeContext(sub_socket, FakeSocket()), receive_timeout_ms=7)

    with pytest.raises(BridgeTimeoutError, match="7 ms"):
        client.receive()

    client.close()


class OrderTrackingContext(FakeContext):
    def __init__(self, calls: list[str], *sockets: FakeSocket) -> None:
        super().__init__(*sockets)
        self.calls = calls

    def socket(self, socket_type: int) -> FakeSocket:
        self.calls.append("sub" if socket_type == zmq.SUB else "req")
        return super().socket(socket_type)


class SnapshotTrackingSocket(FakeSocket):
    def __init__(self, calls: list[str], responses: Any = ()) -> None:
        super().__init__(responses)
        self.calls = calls

    def send(self, payload: bytes) -> None:
        self.calls.append("snapshot")
        super().send(payload)


def test_resynchronize_replaces_subscriber_before_snapshot() -> None:
    calls: list[str] = []
    expected = common_pb2.TimerSnapshot(session_id=7, split_index=1)
    old_sub = FakeSocket()
    req_socket = SnapshotTrackingSocket(calls, [_snapshot_response(1, expected)])
    event = common_pb2.BridgeEvent(
        session_id=7, event_sequence=5, type=common_pb2.EVENT_TIMER_SPLIT
    )
    new_sub = FakeSocket([event.SerializeToString()])
    context = OrderTrackingContext(calls, old_sub, req_socket, new_sub)

    client = BridgeClient(context=context)
    result = client.resynchronize()

    assert result == expected
    assert calls == ["sub", "req", "sub", "snapshot"]
    assert old_sub.closed
    assert not new_sub.closed
    assert client.receive() == event
    client.close()


def test_resynchronize_keeps_new_subscriber_when_snapshot_fails() -> None:
    old_sub = FakeSocket()
    req_socket = FakeSocket(
        [
            encoded_response(
                1,
                error=common_pb2.BridgeError(code=7, message="not attached"),
            ),
            _snapshot_response(2, common_pb2.TimerSnapshot(session_id=7)),
        ]
    )
    new_sub = FakeSocket()
    retry_sub = FakeSocket()
    context = FakeContext(old_sub, req_socket, new_sub, retry_sub)

    client = BridgeClient(context=context)

    with pytest.raises(BridgeRemoteError, match="not attached"):
        client.resynchronize()

    assert old_sub.closed
    assert not new_sub.closed
    assert client.events is not None

    result = client.resynchronize()

    assert new_sub.closed
    assert not retry_sub.closed
    assert result.session_id == 7
    client.close()


class FakeMonotonic:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_resynchronize_recovers_from_event_stream_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeMonotonic()
    monkeypatch.setattr(events_module, "_monotonic", clock)
    old_sub = FakeSocket(poll_result=False)
    snapshot = common_pb2.TimerSnapshot(session_id=7, event_sequence=3)
    req_socket = FakeSocket([_snapshot_response(1, snapshot)])
    heartbeat = common_pb2.BridgeEvent(
        session_id=7,
        event_sequence=3,
        type=common_pb2.EVENT_HEARTBEAT,
    )
    new_sub = FakeSocket([heartbeat.SerializeToString()])
    client = BridgeClient(
        context=FakeContext(old_sub, req_socket, new_sub),
        heartbeat_timeout_ms=100,
    )

    clock.now = 0.15
    with pytest.raises(BridgeEventStreamLostError):
        client.receive()

    clock.now = 0.18
    assert client.resynchronize() == snapshot
    assert client.receive() == heartbeat
    client.close()


def test_close_is_idempotent_and_rejects_operations_and_properties() -> None:
    sub_socket = FakeSocket()
    req_socket = FakeSocket()
    context = FakeContext(sub_socket, req_socket)
    client = BridgeClient(context=context)
    client.close()
    client.close()

    assert sub_socket.closed
    assert req_socket.closed
    assert not context.terminated

    with pytest.raises(BridgeClientError, match="closed"):
        client.snapshot()

    with pytest.raises(BridgeClientError, match="closed"):
        _ = client.rpc

    with pytest.raises(BridgeClientError, match="closed"):
        _ = client.events

    with pytest.raises(BridgeClientError, match="closed"):
        next(client)


def test_external_context_is_not_terminated_on_close() -> None:
    context = FakeContext(FakeSocket(), FakeSocket())
    client = BridgeClient(context=context)

    client.close()

    assert not context.terminated


def test_owned_context_is_terminated_on_close(monkeypatch: pytest.MonkeyPatch) -> None:
    context = FakeContext(FakeSocket(), FakeSocket())
    monkeypatch.setattr(client_module.zmq, "Context", lambda: context)

    client = BridgeClient()
    client.close()

    assert context.terminated


class CloseFailingSocket(FakeSocket):
    def close(self) -> None:
        super().close()
        raise RuntimeError("close boom")


def test_close_cleans_remaining_resources_after_subscriber_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sub_socket = CloseFailingSocket()
    req_socket = FakeSocket()
    context = FakeContext(sub_socket, req_socket)
    monkeypatch.setattr(client_module.zmq, "Context", lambda: context)
    client = BridgeClient()

    with pytest.raises(RuntimeError, match="close boom"):
        client.close()

    assert sub_socket.closed
    assert req_socket.closed
    assert context.terminated
    client.close()


def test_resynchronize_keeps_new_subscriber_when_old_close_fails() -> None:
    old_sub = CloseFailingSocket()
    req_socket = FakeSocket()
    new_sub = FakeSocket()
    client = BridgeClient(context=FakeContext(old_sub, req_socket, new_sub))
    old_subscriber = client.events

    with pytest.raises(RuntimeError, match="close boom"):
        client.resynchronize()

    assert client.events is not old_subscriber
    assert not new_sub.closed
    client.close()


def test_partial_initialization_failure_closes_created_resources() -> None:
    sub_socket = FakeSocket()
    context = FakeContext(sub_socket)

    with pytest.raises(IndexError):
        BridgeClient(context=context)

    assert sub_socket.closed
    assert not context.terminated


def test_partial_initialization_failure_terms_owned_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sub_socket = FakeSocket()
    context = FakeContext(sub_socket)
    monkeypatch.setattr(client_module.zmq, "Context", lambda: context)

    with pytest.raises(IndexError):
        BridgeClient()

    assert sub_socket.closed
    assert context.terminated


class ConnectFailingSocket(FakeSocket):
    def connect(self, endpoint: str) -> None:
        raise RuntimeError("connect boom")


def test_req_connect_failure_closes_subscriber_and_keeps_external_context() -> None:
    sub_socket = FakeSocket()
    req_socket = ConnectFailingSocket()
    context = FakeContext(sub_socket, req_socket)

    with pytest.raises(RuntimeError, match="connect boom"):
        BridgeClient(context=context)

    assert sub_socket.closed
    assert req_socket.closed
    assert not context.terminated


def test_req_connect_failure_terms_owned_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sub_socket = FakeSocket()
    req_socket = ConnectFailingSocket()
    context = FakeContext(sub_socket, req_socket)
    monkeypatch.setattr(client_module.zmq, "Context", lambda: context)

    with pytest.raises(RuntimeError, match="connect boom"):
        BridgeClient()

    assert sub_socket.closed
    assert req_socket.closed
    assert context.terminated
