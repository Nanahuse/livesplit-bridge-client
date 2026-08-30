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
from livesplit_bridge import BridgeClient

with BridgeClient() as client:
    attached = client.attach()
    print(attached.session_id)
    print(client.snapshot())
    client.start()
    client.split()
    client.set_game_time_ticks(123_450_000)  # 12.345 秒（100 ns tick）
```

既定の RPC endpoint は `tcp://127.0.0.1:54000` です。別の endpoint は
`BridgeClient("tcp://127.0.0.1:55000")` のように指定できます。

イベントは同期 iterator として購読できます。受信時は必ず `BridgeEvent.type` を
先に判定してください。

```python
from livesplit_bridge import (
    BridgeEventSubscriber,
    BridgeHeartbeatTimeoutError,
    BridgeTimeoutError,
    common_pb2,
)

try:
    with BridgeEventSubscriber(timeout_ms=5000, heartbeat_timeout_ms=3000) as events:
        for event in events:
            if event.type == common_pb2.EVENT_HEARTBEAT:
                print("heartbeat", event.event_sequence)
            else:
                print(common_pb2.BridgeEventType.Name(event.type), event.snapshot)
except BridgeHeartbeatTimeoutError:
    # 通常処理を止め、BridgeClient.snapshot() などで再同期する
    print("heartbeat timed out")
except BridgeTimeoutError:
    print("event receive timed out")
```

既定のイベント endpoint は `tcp://127.0.0.1:54001` です。timeout を指定しない
場合、`receive()` はイベント到着まで待ちます。

`heartbeat_timeout_ms` を指定すると、subscriber の生成時（SUB 接続完了時）から
ハートビートが受信できなくなるまでの監視期限が始まります。期限は
`EVENT_HEARTBEAT` 受信時のみ延長され、状態イベントでは延長されません。期限切れ
は `BridgeHeartbeatTimeoutError`（`BridgeTimeoutError` の subclass）として発生し
ます。単発 `timeout_ms` の超過は従来どおり `BridgeTimeoutError` です。期限切れ後
は同じ subscriber が引き続き `BridgeHeartbeatTimeoutError` を送出し、監視は再開
されません。通常のイベント処理を止めて subscriber を再生成し、SUB 接続後に
`BridgeClient.snapshot()` などの RPC snapshot で状態を再同期してください。

ハートビートは 1 秒周期で配信され、snapshot を含みません。ハートビート自身は
`event_sequence` の対象外で、最後に送信成功または失敗が確定した sequence 対象
イベントの番号を通知します。

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
