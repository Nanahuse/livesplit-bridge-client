# livesplit-bridge-client

[`LiveSplit.Bridge`](https://github.com/Nanahuse/LiveSplit.Bridge) のPython clientです。
Protocol v3のBinary Protobuf RPCとEvents WebSocketに対応します。

## インストール

```powershell
uv add livesplit-bridge-client
```

## 使い方

```python
from livesplit_bridge import (
    BridgeClient,
    BridgeConnectionLostError,
    BridgeResyncRequiredError,
    common_pb2,
)

with BridgeClient() as client:
    state = client.synchronize(include_completed_count=True)
    timer = state.timer_state
    run = state.run
    attempt = state.attempt
    context = state.context_state
    completed = state.completed_count

    result = client.split()
    print(result)  # 成功時のOperationResponseは空です。失敗時はBridgeRemoteErrorです。

    for event in client:
        if event.type == common_pb2.EVENT_TIMER_SPLIT:
            attempt = client.get_attempt()
        elif event.type == common_pb2.EVENT_TIMER_RESET:
            attempt = client.get_attempt()
            completed = client.get_completed_count()
        elif event.type == common_pb2.EVENT_RUN_CHANGED:
            run = client.get_run()
        elif event.type == common_pb2.EVENT_CONTEXT_CHANGED:
            context = client.get_context_state()
```

`BridgeClient`はEvents WebSocketを先に、RPC WebSocketを次に接続します。初期状態は
`synchronize()`で取得します。複数のQueryを順に実行し、すべてのResponseが同じRuntime
sessionから返った場合だけ`BridgeSyncState`を返します。`completed_count`は通常省略され、
`include_completed_count=True`で取得できます。接続時にsnapshot eventは送られません。
同期中に届いたEventはEvents WebSocketの受信bufferに残り、同期完了後の`receive()`で処理されます。

## QueryとControl

| API | 内容 |
|---|---|
| `get_timer_state()` | 現在のTimer phase、split index、時間 |
| `get_run()` | Run定義、metadata、comparison、segment、icon |
| `get_attempt()` | 現在attemptのsplit時刻とsplit時点のcustom variables |
| `get_context_state()` | 現在のtiming method、comparison、Run custom variables |
| `get_completed_count()` | 完了したattempt数 |

`RunState.metadata.variables`、`ContextState.custom_variables`、
`AttemptSegment.custom_variables`は異なるLiveSplitデータを表します。

`start()`、`split()`、`skip()`、`undo()`、`reset()`、`pause()`、`resume()`と、
Game Time操作は空の`OperationResponse`を返します。Bridgeが返す操作エラーやprotocol errorは
`BridgeRemoteError`として通知されます。成功時のTimerStateが必要な場合は
`get_timer_state()`を呼び出してください。

このclientはState cacheや自動再取得を行いません。`EVENT_TIMER_*`を受けたら必要なQueryを
呼び出し、`EVENT_RUN_CHANGED`では`get_run()`、`EVENT_CONTEXT_CHANGED`では
`get_context_state()`を呼びます。`EVENT_TIMER_SPLIT`後のAttempt更新や、
`EVENT_TIMER_RESET`後のAttempt/CompletedCount更新は呼び出し側の責務です。

## Events

既定の接続先は`ws://127.0.0.1:54000/bridge/v3/rpc`と
`ws://127.0.0.1:54000/bridge/v3/events`です。任意の接続先は次のように指定できます。

```python
client = BridgeClient(
    "ws://127.0.0.1:55000/bridge/v3/rpc",
    "ws://127.0.0.1:55000/bridge/v3/events",
)
```

Timer event（`EVENT_TIMER_STARTED`、`EVENT_TIMER_SPLIT`、`EVENT_TIMER_SKIPPED`、
`EVENT_TIMER_UNDO`、`EVENT_TIMER_RESET`、`EVENT_TIMER_PHASE_CHANGED`）には、LiveSplit
callback時点の`timer_state`が含まれます。`EVENT_RUN_CHANGED`と
`EVENT_CONTEXT_CHANGED`には含まれません。アプリケーションheartbeatはありません。
WebSocket Ping/Pongはtransportのliveness確認に使用されます。

Eventの`session_id`はRuntimeを識別し、`event_sequence`はRuntime内の順序と欠落検出に
使用します。clientは最初に受信したsequenceをbaselineとし、その後の連続性を検証します。
RPCの各Responseにも`session_id`があり、`client.session_id`は直近のResponseの値を返します。
Eventのsequence gap、未知のEvent type、またはRPC/Event sessionの不一致を検出すると、
`BridgeResyncRequiredError`を送出します。保持中のstateを破棄して再同期してください。

`receive(timeout_ms=...)`で単発受信できます。指定時間内にEventがなければ`None`を返します。
timeoutを指定しない場合はEvent到着まで待ちます。Events WebSocketが閉じた場合は
`BridgeConnectionLostError`を送出します。WebSocketライブラリがprotocol ping/pongを処理します。

```python
with BridgeClient() as client:
    event = client.receive(timeout_ms=250)
    if event is not None:
        print(event.session_id, event.event_sequence, event.type)
```

```python
try:
    event = client.receive()
except BridgeResyncRequiredError:
    state = client.synchronize()
```

`reconnect()`は新しいEvents接続、RPC接続の順に確立し、新しい接続上でfull synchronizeを
実行します。成功した場合だけ接続を切り替え、`BridgeSyncState`を返します。接続または同期に
失敗した場合は、新しい接続を閉じて現在の接続を維持します。再接続後のEvent sequenceは新しい
baselineから検証されます。

```python
try:
    event = client.receive()
except BridgeConnectionLostError:
    state = client.reconnect()
```

Control requestは自動再送されません。タイムアウト後に実行結果が不明な場合は、
`synchronize()`または必要なQueryで状態を確認してください。

## 低水準API

RPCだけを使う場合は`BridgeRpcClient`、Event購読だけの場合は`BridgeEventSubscriber`を
利用できます。`BridgeClient`と同じ接続先・timeoutの指定方法です。

```python
from livesplit_bridge import BridgeRpcClient

with BridgeRpcClient() as rpc:
    timer = rpc.get_timer_state()
    run = rpc.get_run()
    context = rpc.get_context_state()
```

```python
from livesplit_bridge import BridgeEventSubscriber

with BridgeEventSubscriber(receive_timeout_ms=5000) as events:
    for event in events:
        print(event.type)
```

## Protocol生成物

Protocol定義の正本は`LiveSplit.Bridge` repositoryです。
`protocol-source.json`は生成元revisionを固定します。protobuf Pythonコードを更新する場合は
次を実行してください。

```powershell
uv run tools/update_protocol.py
```

生成済みの`*_pb2.py`と`*_pb2.pyi`を直接編集しません。生成物は
`src/livesplit/bridge/v3/`に含まれ、`.proto`ファイルと`grpcio-tools`は配布物やruntime
dependencyに含まれません。

## 開発

```powershell
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check --python .venv --error-on-warning
uv build
uv run tools/verify_distributions.py dist
```
