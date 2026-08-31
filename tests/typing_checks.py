from typing import assert_type

from livesplit_bridge import (
    BridgeClient,
    BridgeConnection,
    BridgeEventSubscriber,
    bridge_pb2,
    common_pb2,
)


def check_public_protobuf_types(
    client: BridgeClient, subscriber: BridgeEventSubscriber, request: bridge_pb2.Request
) -> None:
    assert_type(client.request(request), bridge_pb2.Response)
    assert_type(client.attach(), bridge_pb2.AttachResponse)
    assert_type(client.snapshot(), common_pb2.TimerSnapshot)
    assert_type(client.start(), common_pb2.OperationResponse)
    assert_type(client.set_game_time_ticks(1), common_pb2.OperationResponse)
    assert_type(subscriber.receive(), common_pb2.BridgeEvent)
    assert_type(next(subscriber), common_pb2.BridgeEvent)


def check_bridge_connection_types(
    connection: BridgeConnection, request: bridge_pb2.Request
) -> None:
    assert_type(connection.client, BridgeClient)
    assert_type(connection.subscriber, BridgeEventSubscriber)
    assert_type(connection.request(request), bridge_pb2.Response)
    assert_type(connection.attach(), bridge_pb2.AttachResponse)
    assert_type(connection.snapshot(), common_pb2.TimerSnapshot)
    assert_type(connection.timer_operation(common_pb2.TIMER_START), common_pb2.OperationResponse)
    assert_type(connection.start(), common_pb2.OperationResponse)
    assert_type(connection.set_game_time_ticks(1), common_pb2.OperationResponse)
    assert_type(connection.receive(), common_pb2.BridgeEvent)
    assert_type(next(connection), common_pb2.BridgeEvent)
    assert_type(connection.resynchronize(), common_pb2.TimerSnapshot)
