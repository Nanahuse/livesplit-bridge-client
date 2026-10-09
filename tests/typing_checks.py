from typing import assert_type

from livesplit_bridge import (
    BridgeClient,
    BridgeEventSubscriber,
    BridgeRpcClient,
    bridge_pb2,
    common_pb2,
    run_pb2,
)


def check_rpc_client_types(rpc: BridgeRpcClient, request: bridge_pb2.Request) -> None:
    assert_type(rpc.request(request), bridge_pb2.Response)
    assert_type(rpc.session_id, int)
    assert_type(rpc.get_timer_state(), common_pb2.TimerState)
    assert_type(rpc.get_run(), run_pb2.RunState)
    assert_type(rpc.get_attempt(), common_pb2.AttemptState)
    assert_type(rpc.get_context_state(), common_pb2.ContextState)
    assert_type(rpc.get_completed_count(), common_pb2.CompletedCount)
    assert_type(rpc.start(), common_pb2.OperationResponse)
    assert_type(rpc.set_game_time_ticks(1), common_pb2.OperationResponse)


def check_event_subscriber_types(subscriber: BridgeEventSubscriber) -> None:
    assert_type(subscriber.receive(), common_pb2.BridgeEvent | None)
    assert_type(next(subscriber), common_pb2.BridgeEvent)


def check_bridge_client_types(client: BridgeClient, request: bridge_pb2.Request) -> None:
    assert_type(client.rpc, BridgeRpcClient)
    assert_type(client.events, BridgeEventSubscriber)
    assert_type(client.request(request), bridge_pb2.Response)
    assert_type(client.session_id, int)
    assert_type(client.get_timer_state(), common_pb2.TimerState)
    assert_type(client.get_run(), run_pb2.RunState)
    assert_type(client.get_attempt(), common_pb2.AttemptState)
    assert_type(client.get_context_state(), common_pb2.ContextState)
    assert_type(client.get_completed_count(), common_pb2.CompletedCount)
    assert_type(client.timer_operation(common_pb2.TIMER_START), common_pb2.OperationResponse)
    assert_type(client.start(), common_pb2.OperationResponse)
    assert_type(client.set_game_time_ticks(1), common_pb2.OperationResponse)
    assert_type(client.receive(), common_pb2.BridgeEvent | None)
    assert_type(next(client), common_pb2.BridgeEvent)
    assert_type(client.reconnect(), None)
