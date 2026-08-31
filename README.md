# livesplit-bridge-client

[`LiveSplit.Bridge`](https://github.com/Nanahuse/LiveSplit.Bridge) の Python
クライアントです。状態取得とタイマー・ゲーム内時間の操作には ZeroMQ REQ/REP、
イベント購読には PUB/SUB を使用します。

## インストール

```powershell
uv add livesplit-bridge-client
```

source checkout から開発する場合は、最初に protocol submodule を初期化します。

```powershell
git submodule update --init
uv build
```

## 使い方

```python
from livesplit_bridge import BridgeClient, common_pb2

with BridgeClient() as client:
    attached = client.attach()
    print(attached.session_id)

    client.start()
    client.split()
    client.set_game_time_ticks(123_450_000)  # 12.345 秒（100 ns tick）

    for event in client:
        if event.type == common_pb2.EVENT_HEARTBEAT:
            print("heartbeat", event.event_sequence)
        else:
            print(common_pb2.BridgeEventType.Name(event.type), event.snapshot)
```

`BridgeClient` は RPC 操作とイベント購読を 1 つの接続として提供します。内部で
1 つの ZeroMQ context を共有し、SUB の subscriber を先に生成してから RPC client を
生成します。RPC 操作は `BridgeRpcClient` の公開操作をそのまま委譲します（`attach` /
`snapshot` / `timer_operation` / `game_time_operation` と便利メソッド）。イベントは
同期 iterator として受信でき、`receive(timeout_ms=...)` で単発受信もできます。受信
時は必ず `BridgeEvent.type` を先に判定してください。

既定の RPC endpoint は `tcp://127.0.0.1:54000`、イベント endpoint は
`tcp://127.0.0.1:54001` です。別の endpoint は
`BridgeClient("tcp://127.0.0.1:55000", "tcp://127.0.0.1:55001")` のように指定
できます。受信 timeout を指定しない場合、`receive()` はイベント到着まで待ちます。
イベントの単発受信 timeout は `receive(timeout_ms=...)` の呼び出し単位で指定します。
Bridgeからの個々の応答期限は `response_timeout_ms` で指定し、期限内に応答がない
場合は `BridgeResponseTimeoutError` が発生します。

`heartbeat_timeout_ms` を指定すると、subscriber の生成時（SUB 接続完了時）から
ハートビートが受信できなくなるまでの監視期限が始まります。期限は
`EVENT_HEARTBEAT` 受信時のみ延長され、状態イベントでは延長されません。期限切れ
は `BridgeConnectionLostError`（`BridgeClientError` の subclass）として発生し、
heartbeat 欠落により Bridge との接続全体が喪失したことを示します。単発受信
timeout の超過は `BridgeEventReceiveTimeoutError` です
（`BridgeConnectionLostError` とは sibling のため catch 順に依存しません）。
期限切れ後は同じ subscriber が引き続き `BridgeConnectionLostError` を送出し、
監視は再開されません。通常のイベント処理を止め、`reconnect()` で subscriber と
RPC client を再接続し、snapshot で状態を再同期してください。

```python
from livesplit_bridge import BridgeClient, BridgeConnectionLostError

with BridgeClient(heartbeat_timeout_ms=3000) as client:
    while True:
        try:
            event = client.receive()
        except BridgeConnectionLostError:
            snapshot = client.reconnect()
            # subscriber と RPC client は新しいものへ置き換わっている。snapshot を基準に処理を再開する。
            continue
        # event を処理する
```

`reconnect()` は共有する context 上で新しい subscriber を先に、新しい RPC client を
次に生成し、新しい RPC で `snapshot()` を取得してから現在の subscriber / RPC client
を置き換え、`TimerSnapshot` を返します。snapshot 取得に失敗した場合は新しく生成した
subscriber / RPC client をすべて閉じ、現在の subscriber / RPC client を維持するため、
そのまま再試行できます。

`reconnect()` は PUB/SUB と RPC の間で原子的ではありません。新しい subscriber を
接続してから snapshot を取得し、その後に現在の resource と置き換えますが、event gap
や duplicate の除去、返却 snapshot と後続イベントとの順序は保証されません。イベント
を欠落させず厳密に再同期したい場合は呼び出し側で sequence を照合してください。

`BridgeClient`、`BridgeRpcClient`、`BridgeEventSubscriber` はいずれも single-thread
専用です。同一インスタンスを複数スレッドから同時に使わないでください。

ハートビートは 1 秒周期で配信され、snapshot を含みません。ハートビート自身は
`event_sequence` の対象外で、最後に送信成功または失敗が確定した sequence 対象
イベントの番号を通知します。

## 低水準 API

`BridgeRpcClient` と `BridgeEventSubscriber` は `BridgeClient` が内部で使う低水準
クラスです。RPC だけ、またはイベント購読だけを単独で使いたい場合に直接利用します。
`client.rpc` / `client.events` から参照することもできます。

```python
from livesplit_bridge import BridgeRpcClient

with BridgeRpcClient() as rpc:
    rpc.attach()
    rpc.start()
```

```python
from livesplit_bridge import BridgeEventSubscriber

with BridgeEventSubscriber(receive_timeout_ms=5000, heartbeat_timeout_ms=3000) as subscriber:
    for event in subscriber:
        ...
```

低水準の操作では `bridge_pb2` と `common_pb2` を利用できます。enum 値と message
定義はすべて upstream proto から生成され、クライアント側では複製していません。

## protocol の正本と生成物

`external/LiveSplit.Bridge` は Git submodule です。通信契約の唯一の正本は
`external/LiveSplit.Bridge/proto/livesplit/bridge/v1/*.proto` です。

`*_pb2.py` と `*_pb2.pyi` は build 時にこの proto から生成し、wheel と sdist に
収録します。生成物は Git には追加しません。インストール時や実行時のコード生成は
行わず、`grpcio-tools` は runtime dependency に含めません。

## 開発

```powershell
uv init --bare --no-workspace .tmp/test-project
uv add --project .tmp/test-project . pytest
uv run --project .tmp/test-project pytest -q tests
uv build
uv run tools/generate_protocol_stubs.py --output .tmp/protocol-stubs
uv run tools/verify_distributions.py dist
```
