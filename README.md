# livesplit-bridge-client

[`LiveSplit.Bridge`](https://github.com/Nanahuse/LiveSplit.Bridge) のPython clientです。
Protocol v3のBinary Protobuf RPCとEvents WebSocketに対応します。

## インストール

```powershell
uv add livesplit-bridge-client
```

## 使い方

```python
from livesplit_bridge import BridgeClient, common_pb2

with BridgeClient() as client:
    # Events接続はBridgeClientの生成時に始まります。イベント受信を開始し、
    # 初期Query中に届いたイベントは呼び出し側でqueueしてください。
    timer = client.get_timer_state()
    run = client.get_run()
    attempt = client.get_attempt()
    context = client.get_context_state()
    completed = client.get_completed_count()

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
`get_timer_state()`、`get_run()`、`get_attempt()`、`get_context_state()`、
`get_completed_count()`で取得してください。接続時にBridgeからsnapshot eventは届きません。
初期Queryと並行して届いたEventは、Query結果を反映してから処理できるよう呼び出し側で
一時queueに保持してください。

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
使用します。sequenceは1から始まり、revisionではありません。RPCの各Responseにも
`session_id`があり、`client.session_id`は直近の成功したRPC応答の値を返します。

`receive(timeout_ms=...)`で単発受信できます。指定時間内にEventがなければ`None`を返します。
timeoutを指定しない場合はEvent到着まで待ちます。Events WebSocketが閉じた場合は
`BridgeConnectionLostError`を送出します。WebSocketライブラリがprotocol ping/pongを処理します。

```python
with BridgeClient() as client:
    event = client.receive(timeout_ms=250)
    if event is not None:
        print(event.session_id, event.event_sequence, event.type)
```

`reconnect()`は新しいEvents/RPC接続を作り、接続を入れ替えます。snapshot queryは実行しません。
2つのWebSocketをまたぐ処理はatomicではないため、再接続前後のEvent欠落や重複は呼び出し側で
`session_id`と`event_sequence`を使って扱ってください。

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
