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

イベントは同期 iterator として購読できます。

```python
from livesplit_bridge import BridgeEventSubscriber, common_pb2

with BridgeEventSubscriber(timeout_ms=5000) as events:
    for event in events:
        print(common_pb2.BridgeEventType.Name(event.type), event.snapshot)
```

既定のイベント endpoint は `tcp://127.0.0.1:54001` です。timeout を指定しない
場合、`receive()` はイベント到着まで待ちます。

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
uv venv .venv
uv pip install --python .venv . pytest
.\.venv\Scripts\pytest.exe -q tests
uv build
uv run tools/generate_protocol_stubs.py --output .tmp/protocol-stubs
uv run tools/verify_distributions.py dist
```
