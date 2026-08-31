from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
import zmq

from livesplit_bridge import (
    BridgeClient,
    BridgeProtocolError,
    BridgeRemoteError,
    BridgeTimeoutError,
    bridge_pb2,
    common_pb2,
)


class FakeSocket:
    def __init__(
        self,
        responses: Iterable[bytes] = (),
        *,
        poll_result: bool = True,
    ) -> None:
        self.responses = list(responses)
        self.poll_result = poll_result
        self.sent: list[bytes] = []
        self.options: list[tuple[int, object]] = []
        self.endpoint: str | None = None
        self.closed = False

    def setsockopt(self, option: int, value: object) -> None:
        self.options.append((option, value))

    def connect(self, endpoint: str) -> None:
        self.endpoint = endpoint

    def send(self, payload: bytes) -> None:
        self.sent.append(payload)

    def poll(self, timeout: int, flags: int) -> bool:
        assert flags == zmq.POLLIN
        return self.poll_result

    def recv(self) -> bytes:
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self, *sockets: FakeSocket) -> None:
        self.sockets = list(sockets)
        self.socket_types: list[int] = []
        self.terminated = False

    def socket(self, socket_type: int) -> FakeSocket:
        self.socket_types.append(socket_type)
        return self.sockets.pop(0)

    def term(self) -> None:
        self.terminated = True


def encoded_response(request_id: int, **body: Any) -> bytes:
    return bridge_pb2.Response(
        protocol_version=1,
        request_id=request_id,
        **body,
    ).SerializeToString()


def test_snapshot_sends_versioned_request_and_returns_snapshot() -> None:
    expected = common_pb2.TimerSnapshot(session_id=42, split_index=3)
    socket = FakeSocket(
        [
            encoded_response(
                1,
                get_snapshot=bridge_pb2.GetSnapshotResponse(snapshot=expected),
            )
        ]
    )
    context = FakeContext(socket)

    with BridgeClient(context=context) as client:
        actual = client.snapshot()

    request = bridge_pb2.Request.FromString(socket.sent[0])
    assert request.protocol_version == 1
    assert request.request_id == 1
    assert request.HasField("get_snapshot")
    assert actual == expected
    assert socket.closed
    assert not context.terminated


def test_convenience_timer_operation_uses_proto_enum() -> None:
    socket = FakeSocket([encoded_response(1, operation=common_pb2.OperationResponse(success=True))])
    client = BridgeClient(context=FakeContext(socket))

    result = client.start()

    request = bridge_pb2.Request.FromString(socket.sent[0])
    assert request.timer_operation.operation == common_pb2.TIMER_START
    assert result.success
    client.close()


def test_game_time_ticks_preserve_optional_presence() -> None:
    socket = FakeSocket([encoded_response(1, operation=common_pb2.OperationResponse(success=True))])
    client = BridgeClient(context=FakeContext(socket))

    client.set_game_time_ticks(123_450_000)

    request = bridge_pb2.Request.FromString(socket.sent[0])
    assert request.game_time_operation.operation == common_pb2.SET
    assert request.game_time_operation.HasField("ticks")
    assert request.game_time_operation.ticks == 123_450_000
    client.close()


def test_remote_error_exposes_code_and_message() -> None:
    socket = FakeSocket(
        [
            encoded_response(
                1,
                error=common_pb2.BridgeError(code=7, message="not attached"),
            )
        ]
    )
    client = BridgeClient(context=FakeContext(socket))

    with pytest.raises(BridgeRemoteError, match="not attached") as error:
        client.attach()

    assert error.value.code == 7
    client.close()


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (encoded_response(99), "Request ID mismatch"),
        (
            bridge_pb2.Response(protocol_version=2, request_id=1).SerializeToString(),
            "Protocol version mismatch",
        ),
    ],
)
def test_protocol_mismatch_is_rejected(response: bytes, message: str) -> None:
    client = BridgeClient(context=FakeContext(FakeSocket([response])))

    with pytest.raises(BridgeProtocolError, match=message):
        client.attach()

    client.close()


def test_timeout_recreates_req_socket() -> None:
    timed_out = FakeSocket(poll_result=False)
    replacement = FakeSocket()
    client = BridgeClient(context=FakeContext(timed_out, replacement), timeout_ms=12)

    with pytest.raises(BridgeTimeoutError, match="12 ms"):
        client.attach()

    assert timed_out.closed
    assert replacement.endpoint == client.rpc_endpoint
    client.close()
    assert replacement.closed


def test_close_is_idempotent_and_closed_client_rejects_requests() -> None:
    socket = FakeSocket()
    client = BridgeClient(context=FakeContext(socket))
    client.close()
    client.close()

    with pytest.raises(RuntimeError, match="closed"):
        client.attach()


class ConnectFailingSocket(FakeSocket):
    def connect(self, endpoint: str) -> None:
        raise RuntimeError("connect boom")


class SetSockoptFailingSocket(FakeSocket):
    def setsockopt(self, option: int, value: object) -> None:
        raise RuntimeError("setsockopt boom")


@pytest.mark.parametrize("bad_socket", [ConnectFailingSocket(), SetSockoptFailingSocket()])
def test_connect_failure_closes_socket_but_keeps_external_context(bad_socket: FakeSocket) -> None:
    context = FakeContext(bad_socket)

    with pytest.raises(RuntimeError):
        BridgeClient(context=context)

    assert bad_socket.closed
    assert not context.terminated


@pytest.mark.parametrize("bad_socket", [ConnectFailingSocket(), SetSockoptFailingSocket()])
def test_connect_failure_closes_socket_and_terms_owned_context(
    bad_socket: FakeSocket, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = FakeContext(bad_socket)
    monkeypatch.setattr(zmq, "Context", lambda: context)

    with pytest.raises(RuntimeError):
        BridgeClient()

    assert bad_socket.closed
    assert context.terminated
