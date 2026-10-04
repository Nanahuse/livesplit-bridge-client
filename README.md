# livesplit-bridge-client

[`LiveSplit.Bridge`](https://github.com/Nanahuse/LiveSplit.Bridge) の Python
クライアントです。Protocol v2 に対応し、状態取得とタイマー・ゲーム内時間の操作には
RPC 用 WebSocket、イベント購読には Events 用 WebSocket を使用します。Payload は
Binary Protobuf です。v1 プロトコルとの互換性はありません。

## インストール

```powershell
uv add livesplit-bridge-client
```

### protocol の更新

protocol 定義の正本は [LiveSplit.Bridge](https://github.com/Nanahuse/LiveSplit.Bridge)
にあり、`protocol-source.json` で revision を固定しています。生成済みの
protobuf Python コードを更新する場合は、以下を実行します。

```powershell
uv run tools/update_protocol.py
```

## 使い方

```python
from livesplit_bridge import BridgeClient, common_pb2

with BridgeClient() as client:
    attached = client.attach()
    print(attached.session_id)

    run = client.get_run()
    attempt = client.get_attempt()
    runtime = client.get_runtime_state()

    result = client.split()
    if result.success:
        print(result.timer_state.split_index)

    for event in client:
        if event.type == common_pb2.EVENT_HEARTBEAT:
            print("heartbeat", event.event_sequence)
            continue

        if event.HasField("timer_state"):
            print(event.timer_state)
```

`BridgeClient` は RPC 操作とイベント購読を 1 つの統合 API として提供します。内部では
Events 用 WebSocket を先に接続してから RPC 用 WebSocket を接続し、合計 2 本の
WebSocket 接続を保持します。RPC 操作は `BridgeRpcClient` の公開操作をそのまま委譲
します。イベントは同期 iterator として受信でき、`receive(timeout_ms=...)` で単発受信も
できます。受信時は必ず `BridgeEvent.type` を先に判定してください。

### 状態モデル

Protocol v2 では状態を役割ごとに分離しています。必要な状態だけを必要な頻度で取得します。

| 状態 | 取得 API | 内容 |
|---|---|---|
| `TimerState` | `get_timer_state()` | 高頻度で変化するライブタイマー状態 |
| `RunState` | `get_run()` | Run 定義や Comparison など比較的静的な情報 |
| `AttemptState` | `get_attempt()` | 現在 Attempt に依存する情報 |
| `RuntimeState` | `get_runtime_state()` | LiveSplit の現在設定・UI 状態 |

`attach()` は `session_id` と現在の `timer_state` を返します。

```python
attached = client.attach()
timer_state = attached.timer_state
```

`get_timer_state()` は高頻度 Timer 表示向けの軽量 API です。`TimerState` には
`state_revision`、`phase`、`split_index`、時間値、および `run_revision` /
`attempt_revision` / `runtime_revision` が含まれます。`event_sequence` や `split_count`
は `TimerState` には含まれません。Split 数は `RunState.segments` から、Pause 状態は
`phase` から判断してください。

### イベントと revision

イベントは `/bridge/v2/events` へ接続したすべてのクライアントへ broadcast されます。
状態変更イベントにはその時点の `timer_state` が含まれます。heartbeat は 1 秒周期で
配信され、`timer_state` を持ちません。`event.type == common_pb2.EVENT_HEARTBEAT` で
判定してください。

クライアント自身は revision に応じた自動再取得や State cache を持ちません。どの状態を
いつ再取得するかは呼び出し側が決めます。`TimerState` の revision を監視し、変化した
ときだけ対応する RPC を呼ぶのが基本パターンです。

```python
from livesplit_bridge import BridgeClient, common_pb2

with BridgeClient() as client:
    attached = client.attach()
    timer_state = attached.timer_state
    run = client.get_run()
    attempt = client.get_attempt()
    runtime = client.get_runtime_state()

    for event in client:
        if event.type == common_pb2.EVENT_HEARTBEAT:
            continue
        if not event.HasField("timer_state"):
            continue

        timer_state = event.timer_state
        if timer_state.run_revision != run.run_revision:
            run = client.get_run()
        if timer_state.attempt_revision != attempt.attempt_revision:
            attempt = client.get_attempt()
        if timer_state.runtime_revision != runtime.runtime_revision:
            runtime = client.get_runtime_state()
```

### operation

タイマー・ゲーム内時間の操作は `OperationResponse` を返します。成功時は
`OperationResponse.timer_state` に操作後の `TimerState` が入ります。クライアント側で
追加の `get_timer_state()` を自動実行しません。

```python
result = client.start()
if result.success:
    print(result.message, result.timer_state.phase)
```

利用できる操作は `timer_operation()` / `game_time_operation()` と、その便利メソッド
（`start` / `split` / `skip` / `undo` / `reset` / `pause` / `resume` /
`initialize_game_time` / `set_game_time_ticks` / `pause_game_time` /
`resume_game_time`）です。

### endpoint と timeout

既定の RPC endpoint は `ws://127.0.0.1:54000/bridge/v2/rpc`、イベント endpoint は
`ws://127.0.0.1:54000/bridge/v2/events` です。別の endpoint は
`BridgeClient("ws://127.0.0.1:55000/bridge/v2/rpc", "ws://127.0.0.1:55000/bridge/v2/events")`
のように指定できます。v1 endpoint への fallback は行いません。受信 timeout を指定しない
場合、`receive()` はイベント到着まで待ちます。イベントの単発受信 timeout は
`receive(timeout_ms=...)` の呼び出し単位で指定します。指定時間内にイベントがなければ、
正常な待機結果として `None` を返します。Bridge からの個々の応答期限は
`response_timeout_ms` で指定し、期限内に応答がない場合は `BridgeResponseTimeoutError`
が発生します。RPC が timeout した場合、RPC WebSocket は安全のため再生成されます。

### heartbeat 監視

`heartbeat_timeout_ms` を指定すると、subscriber の生成時（Events WebSocket 接続完了時）
からハートビートが受信できなくなるまでの監視期限が始まります。期限は
`EVENT_HEARTBEAT` 受信時のみ延長され、状態イベントでは延長されません。期限切れは
`BridgeConnectionLostError`（`BridgeClientError` の subclass）として発生し、heartbeat
欠落により Bridge との接続全体が喪失したことを示します。Events WebSocket が Bridge 側
から close された場合も同様に `BridgeConnectionLostError` として検出します。単発受信
timeout は接続障害ではないため例外にはならず、`receive()` が `None` を返します。期限切れ
後は同じ subscriber が引き続き `BridgeConnectionLostError` を送出し、監視は再開されません。
通常のイベント処理を止め、`reconnect()` で再接続し、状態を再同期してください。

```python
from livesplit_bridge import BridgeClient, BridgeConnectionLostError

with BridgeClient(heartbeat_timeout_ms=3000) as client:
    while True:
        try:
            event = client.receive(timeout_ms=250)
        except BridgeConnectionLostError:
            attached = client.reconnect()
            # 新しい session_id / timer_state を基準に処理を再開する。
            continue
        if event is None:
            # 今回の待機中にイベントはなかった。
            continue
        # event を処理する
```

### reconnect

`reconnect()` は新しい Events WebSocket を先に、新しい RPC WebSocket を次に接続し、
新しい RPC で `attach()` を実行してから現在の subscriber / RPC client を置き換え、
`AttachResponse` を返します。返却されるのは `TimerState` 単体ではなく `AttachResponse`
です。呼び出し側は `attached.session_id` / `attached.timer_state` を利用してください。

```python
attached = client.reconnect()
print(attached.session_id)
timer_state = attached.timer_state
```

接続または `attach()` に失敗した場合は、新しく生成した Events / RPC WebSocket をすべて
閉じ、現在の接続を維持するため、そのまま再試行できます。成功時は旧 Events WebSocket を
先に、旧 RPC WebSocket を次に閉じます。

`reconnect()` は Events と RPC の 2 接続の間で原子的ではありません。Events WebSocket を
接続してから `attach()` が完了するまでの間に event が到着する可能性があります。event
gap / duplicate の自動除去は行わず、返却された `AttachResponse` と後続イベントとの順序も
保証されません。厳密に再同期したい場合は呼び出し側で `session_id` / `event_sequence` を
照合してください。

### State cache を持たない

Protocol v2 の `TimerState` / `RunState` / `AttemptState` / `RuntimeState` は revision で
関連付けられますが、このクライアント自身は Run / Attempt / Runtime のキャッシュ、revision
変更による自動 RPC、自動再同期を実装しません。このクライアントの責務は WebSocket
transport と Protobuf RPC/Event wrapper までです。どの状態をいつ再取得するかは利用側に
任せます。

`BridgeClient`、`BridgeRpcClient`、`BridgeEventSubscriber` はいずれも single-thread
専用です。同一インスタンスを複数スレッドから同時に使わないでください。

## 低水準 API

`BridgeRpcClient` と `BridgeEventSubscriber` は `BridgeClient` が内部で使う低水準
クラスです。RPC だけ、またはイベント購読だけを単独で使いたい場合に直接利用します。
`client.rpc` / `client.events` から参照することもできます。

```python
from livesplit_bridge import BridgeRpcClient

with BridgeRpcClient() as rpc:
    attached = rpc.attach()
    timer_state = rpc.get_timer_state()
    run = rpc.get_run()
    rpc.start()
```

```python
from livesplit_bridge import BridgeEventSubscriber

with BridgeEventSubscriber(receive_timeout_ms=5000, heartbeat_timeout_ms=3000) as subscriber:
    for event in subscriber:
        ...
```

低水準の操作では `bridge_pb2`、`common_pb2`、`run_pb2` を利用できます。enum 値と
message 定義はすべて upstream proto から生成され、クライアント側では複製していません。

## protocol の正本と生成物

通信契約の正本は `LiveSplit.Bridge` リポジトリの
`proto/livesplit/bridge/v2/*.proto` だけです。本リポジトリは `.proto` を
保持せず、`protocol-source.json` に固定した revision から生成した
`*_pb2.py` / `*_pb2.pyi` を `src/livesplit/bridge/v2/` に commit して管理します。

`*_pb2.py` / `*_pb2.pyi` は generated code であり直接編集しません。protocol
を更新する場合は `LiveSplit.Bridge` 側で `.proto` を変更し、commit SHA を
`protocol-source.json` に反映してから `uv run tools/update_protocol.py` で
再生成します。build 時や install 時のコード生成は行わず、`grpcio-tools` は
runtime dependency に含めません。

## 開発

```powershell
uv init --bare --no-workspace .tmp/test-project
uv add --project .tmp/test-project . pytest
uv run --project .tmp/test-project pytest -q tests
uv build
uv run tools/verify_distributions.py dist
```
