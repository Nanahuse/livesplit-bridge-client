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
from livesplit_bridge import BridgeConnection, common_pb2

with BridgeConnection() as connection:
    attached = connection.attach()
    print(attached.session_id)

    connection.start()
    connection.split()
    connection.set_game_time_ticks(123_450_000)  # 12.345 秒（100 ns tick）

    for event in connection:
        if event.type == common_pb2.EVENT_HEARTBEAT:
            print("heartbeat", event.event_sequence)
        else:
            print(common_pb2.BridgeEventType.Name(event.type), event.snapshot)
```

`BridgeConnection` は RPC 操作とイベント購読を 1 つの接続として提供します。内部で
1 つの ZeroMQ context を共有し、SUB の subscriber を先に生成してから RPC client を
生成します。RPC 操作は `BridgeClient` の公開操作をそのまま委譲します（`attach` /
`snapshot` / `timer_operation` / `game_time_operation` と便利メソッド）。イベントは
同期 iterator として受信でき、`receive(timeout_ms=...)` で単発受信もできます。受信
時は必ず `BridgeEvent.type` を先に判定してください。

既定の RPC endpoint は `tcp://127.0.0.1:54000`、イベント endpoint は
`tcp://127.0.0.1:54001` です。別の endpoint は
`BridgeConnection("tcp://127.0.0.1:55000", "tcp://127.0.0.1:55001")` のように指定
できます。受信 timeout を指定しない場合、`receive()` はイベント到着まで待ちます。
subscriber の既定 timeout はコンストラクタの `receive_timeout_ms` で指定し、
`receive(timeout_ms=...)` で単発上書きできます。

`heartbeat_timeout_ms` を指定すると、subscriber の生成時（SUB 接続完了時）から
ハートビートが受信できなくなるまでの監視期限が始まります。期限は
`EVENT_HEARTBEAT` 受信時のみ延長され、状態イベントでは延長されません。期限切れ
は `BridgeEventStreamLostError`（`BridgeClientError` の subclass）として発生し、
event stream が heartbeat 欠落により信頼不能になったことを示します。単発受信
timeout の超過は従来どおり `BridgeTimeoutError` です（`BridgeEventStreamLostError`
とは sibling のため catch 順に依存しません）。期限切れ後は同じ subscriber が
引き続き `BridgeEventStreamLostError` を送出し、監視は再開されません。通常の
イベント処理を止め、`resynchronize()` で subscriber を再接続し、RPC snapshot で
状態を再同期してください。

```python
from livesplit_bridge import BridgeConnection, BridgeEventStreamLostError

with BridgeConnection(heartbeat_timeout_ms=3000) as connection:
    while True:
        try:
            event = connection.receive()
        except BridgeEventStreamLostError:
            snapshot = connection.resynchronize()
            # subscriber は新しいものへ置き換わっている。snapshot を基準に処理を再開する。
            continue
        # event を処理する
```

`resynchronize()` は新しい subscriber を生成して置き換えてから `snapshot()` を呼び、
`TimerSnapshot` を返します。snapshot 取得に失敗した場合も新しい subscriber は維持
されるため、そのまま再試行できます。

`resynchronize()` は PUB/SUB と RPC の間で原子的ではありません。subscriber を SUB
置換後に snapshot を取得しますが、event gap や duplicate の除去、返却 snapshot と
後続イベントとの順序は保証されません。イベントを欠落させず厳密に再同期したい場合は
呼び出し側で sequence を照合してください。

`BridgeConnection`、`BridgeClient`、`BridgeEventSubscriber` はいずれも single-thread
専用です。同一インスタンスを複数スレッドから同時に使わないでください。

ハートビートは 1 秒周期で配信され、snapshot を含みません。ハートビート自身は
`event_sequence` の対象外で、最後に送信成功または失敗が確定した sequence 対象
イベントの番号を通知します。

## 低水準 API

`BridgeClient` と `BridgeEventSubscriber` は `BridgeConnection` が内部で使う低水準
クラスです。RPC だけ、またはイベント購読だけを単独で使いたい場合に直接利用します。
`connection.client` / `connection.subscriber` から参照することもできます。

```python
from livesplit_bridge import BridgeClient

with BridgeClient() as client:
    client.attach()
    client.start()
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
