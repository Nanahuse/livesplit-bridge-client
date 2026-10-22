# livesplit-bridge-client

[`LiveSplit.Bridge`](https://github.com/Nanahuse/LiveSplit.Bridge) の同期 Python client です。
0.6.0 は JSON Protocol v4 の RPC / Events WebSocket に対応します。Python 3.11 以降が必要です。
旧 Protobuf Protocol との互換性や自動判定はありません。

## インストール

```powershell
uv add livesplit-bridge-client
```

## 使い方

```python
from livesplit_bridge import BridgeClient, EventType, TimerPhase

with BridgeClient() as client:
    state = client.synchronize(include_completed_count=True)
    timer = state.timer_state  # TimerState (Pydantic v2)
    run = state.run  # RunState
    attempt = state.attempt  # AttemptState
    context = state.context_state  # ContextState
    completed = state.completed_count  # CompletedCount | None

    print(run.game_name, timer.phase, timer.real_time_ticks)
    if timer.phase == TimerPhase.NOT_RUNNING:
        client.start()  # 成功時は None、失敗時は BridgeRemoteError

    for event in client:
        if event.type == EventType.TIMER_SPLIT:
            attempt = client.get_attempt()
        elif event.type == EventType.TIMER_RESET:
            attempt = client.get_attempt()
            completed = client.get_completed_count()
        elif event.type == EventType.RUN_CHANGED:
            run = client.get_run()
        elif event.type == EventType.CONTEXT_CHANGED:
            context = client.get_context_state()
```

`BridgeClient` は Events、RPC の順で接続します。初期状態は `synchronize()` で取得します。
これは複数の Query を順に実行し、同一 Session の結果を `BridgeSyncState` にまとめる処理です。
全結果が同じ時点の Snapshot である保証はありません。`completed_count` は
`include_completed_count=True` の場合だけ取得します。アイコンは同期対象に含めません。
接続時に Snapshot Event は送られず、同期中に届いた Event は受信 buffer に残ります。

全 client は単一 thread で利用してください。非同期 API、自動 State cache、Control 再送はありません。

## Query と Control

| API | 型付き戻り値 | 内容 |
| --- | --- | --- |
| `get_timer_state()` | `TimerState` | phase、split index、現在時刻、Game Time の状態 |
| `get_run()` | `RunState` | Run 定義、metadata、comparison、segment（画像を含まない） |
| `get_run_icons()` | `RunIcons` | ゲームアイコンと Segment 順のアイコン |
| `get_attempt()` | `AttemptState` | 現在 attempt の split 時刻と split 時点の custom variables |
| `get_context_state()` | `ContextState` | timing method、comparison、Run custom variables |
| `get_completed_count()` | `CompletedCount` | 完了した attempt 数 |

これらのモデルと関連構造体・enum は `livesplit_bridge` から import できます。生の `dict` は返しません。
JSON の必須フィールド、null の可否、enum、整数範囲、未知のプロパティを Pydantic v2 で検証します。
JSON の重複プロパティも拒否します。時間値は 100 ナノ秒単位の signed int64 ticks で、負値も有効です。
`TimerPhase`、`TimingMethod`、`EventType`、`BridgeErrorCode` などは文字列 enum です。

`RunState.metadata.variables`、`ContextState.custom_variables`、
`AttemptSegment.custom_variables` はそれぞれ別の LiveSplit データを表します。

`start()`、`split()`、`skip()`、`undo()`、`reset()`、`pause()`、`resume()` と、
`initialize_game_time()`、`set_game_time_ticks(ticks)`、`pause_game_time()`、
`resume_game_time()` は成功時に `None` を返します（wire 上は `result: null`）。
Game Time の `set` には ticks が必須で、それ以外の操作には指定できません。
成功後の状態が必要なら `get_timer_state()` を呼び出してください。

Bridge の有効なエラー応答は `BridgeRemoteError` です。`code` に文字列コード、`message` に
サーバーのメッセージを保持します。コードは `invalid_request`、`invalid_argument`、
`operation_failed`、`internal_error`、`permission_denied` です。通常、接続は維持されます。
ただしエラー応答でも Session が変わった場合、統合 client は再接続を要求します。

## アイコン

```python
from pathlib import Path
from livesplit_bridge import BridgeClient

with BridgeClient() as client:
    icons = client.get_run_icons()
    if icons.game_icon is not None:
        Path("game.png").write_bytes(icons.game_icon)
    for index, png in enumerate(icons.segment_icons):
        if png is not None:
            Path(f"segment-{index}.png").write_bytes(png)
```

`game_icon` は `bytes | None`、`segment_icons` は `list[bytes | None]` です。
Base64 をデコードした PNG bytes を返し、画像がない Segment も `None` として位置を保持します。
配列自体は常に存在し、null にはなりません。取得は呼び出したときだけ行い、自動 cache はありません。

`get_run()` と `get_run_icons()` は別要求で、間に Run が切り替わる場合があります。
結果を結び付ける専用 revision はありません。`run_changed` では必要に応じて再取得してください。
アイコンだけの変更には専用 Event や変更検出がないため、再取得のタイミングは呼び出し側で判断します。

## Events

既定の接続先は `ws://127.0.0.1:54000/bridge/v4/rpc` と
`ws://127.0.0.1:54000/bridge/v4/events` です。任意の接続先も指定できます。

```python
client = BridgeClient(
    "ws://127.0.0.1:55000/bridge/v4/rpc",
    "ws://127.0.0.1:55000/bridge/v4/events",
)
```

すべての Event に `session_id`、`event_sequence`、`type`、`timer_state` が必須です。

| `EventType` | wire の type | `timer_state` |
| --- | --- | --- |
| `TIMER_STARTED` | `timer_started` | `TimerState` |
| `TIMER_SPLIT` | `timer_split` | `TimerState` |
| `TIMER_SKIPPED` | `timer_skipped` | `TimerState` |
| `TIMER_UNDO` | `timer_undo` | `TimerState` |
| `TIMER_PHASE_CHANGED` | `timer_phase_changed` | `TimerState` |
| `TIMER_RESET` | `timer_reset` | `TimerState` または `None` |
| `RUN_CHANGED` | `run_changed` | `None` |
| `CONTEXT_CHANGED` | `context_changed` | `None` |

TimerState は LiveSplit callback 時点の値です。Reset 時に capture できなかった場合は
`timer_state: null` になるため、必要なら Query してください。

Event は再取得のきっかけとして扱います。履歴再送や全通知の配送保証はありません。
Attempt / CompletedCount の更新、Run / Context の再取得は呼び出し側の責務です。
アプリケーション heartbeat はなく、WebSocket ライブラリが Ping/Pong を処理します。

`receive(timeout_ms=250)` は時間内に Event がなければ `None` を返します。
指定しない場合は到着まで待機します。iterator は Event が届くまで待ちます。

## 再同期と再接続

`session_id` は非ゼロ uint32 の Runtime 識別子です。`client.session_id` は直近の有効な RPC 応答の
値を返し、初回応答前は 0 です。RPC Request ID は uint32 で、最大値の次は 0 に循環します。
RPC は ID 対応と要求したメソッドに対する結果型を検証します。

`event_sequence` は非ゼロ uint32 で、最大値 `4294967295` の次は 1 に循環します。
最初の Event を baseline とし、その後の連続性を検証します。

| `recovery_state` | 原因 | 復旧方法 |
| --- | --- | --- |
| `HEALTHY` | 通常処理 | そのまま利用 |
| `RESYNC_REQUIRED` | sequence の欠落・重複・逆順、不正な Event | `synchronize()` |
| `RECONNECT_REQUIRED` | RPC 通信異常、Events 切断、RPC / Events の Session 不一致・変更 | `reconnect()` |

sequence の不連続は `BridgeResyncRequiredError`、Session 不一致は
`BridgeReconnectRequiredError`、Events 切断は `BridgeConnectionLostError` です。
不正な JSON、Binary frame、必須フィールド・型・範囲の違反は `BridgeProtocolError` です。
Event の検証違反では再同期、RPC の検証違反では socket を破棄して再接続を要求します。
RPC timeout は `BridgeResponseTimeoutError`、その他の通信障害は `BridgeClientError` となります。

```python
from livesplit_bridge import (
    BridgeClientError,
    BridgeConnectionLostError,
    BridgeProtocolError,
    BridgeReconnectRequiredError,
    BridgeRecoveryState,
    BridgeRemoteError,
    BridgeResyncRequiredError,
)

try:
    event = client.receive(timeout_ms=250)
except BridgeReconnectRequiredError:
    state = client.reconnect()
except BridgeResyncRequiredError:
    state = client.synchronize()
except BridgeConnectionLostError:
    state = client.reconnect()
except BridgeProtocolError:
    if client.recovery_state == BridgeRecoveryState.RECONNECT_REQUIRED:
        state = client.reconnect()
    else:
        state = client.synchronize()
except BridgeRemoteError as error:
    print(error.code, error.message)
except BridgeClientError:
    state = client.reconnect()
```

復旧が必要な間は Query、Control、Events 受信を停止します。`synchronize()` は
`RECONNECT_REQUIRED` では拒否されます。同期成功後に sequence baseline を解除し、次の Event から
連続性を検証します。既に buffer に届いた Event は破棄しません。

`reconnect()` は新しい Events、RPC の順で接続して Query 結果を集め、同一 Session であることを
確認してから切り替えます。全結果が同じ時点の Snapshot である保証はありません。
新しい接続や同期が失敗した場合はその接続を閉じ、従来の接続と復旧状態を保持します。
新しい Events の Session は最初の受信で確定し、RPC と不一致なら再び再接続を要求します。

Control は Game Time 操作を含め自動再送しません。応答を受け取れなかった操作の実行結果は
不明なので、再接続後に状態を Query して呼び出し側で判断してください。

## 低水準 API

RPC 単体は `BridgeRpcClient`、Event 購読単体は `BridgeEventSubscriber` を利用できます。
低水準の Event 購読はモデルを検証しますが、Session / sequence の連続性を管理しません。
両接続をまたぐ管理には `BridgeClient` を使用してください。
RPC 単体では通信異常後に socket を破棄し、暗黙の再接続や再送は行いません。

```python
from livesplit_bridge import BridgeRpcClient, QueryMethod, QueryRequest

with BridgeRpcClient(response_timeout_ms=3000) as rpc:
    timer = rpc.get_timer_state()
    response = rpc.request(QueryRequest(request_id=0, method=QueryMethod.GET_RUN))
    print(response.result)  # 検証済みの型付きモデル。request_id は client が採番します。
```

```python
from livesplit_bridge import BridgeEventSubscriber

with BridgeEventSubscriber(receive_timeout_ms=5000) as events:
    for event in events:
        print(event.type, event.timer_state)
```

## Schema と開発

Protocol の正本は Bridge の C# DTO と、そこから生成された
[`公式 JSON Schema`](https://github.com/Nanahuse/LiveSplit.Bridge/tree/v4/schemas/v4) です。
`protocol-source.json` が参照コミットを固定します。

```powershell
uv run tools/update_protocol.py
uv run tools/update_protocol.py --check
```

3 つの Schema を `schemas/v4/` へ同期し、公式の不正入力 fixture も更新します。
実行時は Pydantic モデルで検証し、Schema や `jsonschema` は runtime 依存に含めません。
モデルは `src/livesplit_bridge/models.py` で明示的に管理し、独自の型生成処理はありません。
契約テストは公式 C# シリアライズ結果・不正入力・各階層の必須フィールド・null・enum・整数境界を
公式 Schema と照合します。

```powershell
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run ty check --python .venv --error-on-warning
uv build
uv run tools/verify_distributions.py dist
```

Windows と .NET 10 SDK があれば、固定済み Bridge を取得・ビルドして実通信テストも実行できます。
通常の pytest はこのテストを skip します。CI では Windows / Python 3.11・3.14 の両方で実行します。
Bridge の仕様やソースに変更は加えません。

```powershell
uv run tools/run_integration.py
# 既存の固定コミットの checkout を使う場合
uv run tools/run_integration.py --source C:/path/to/LiveSplit.Bridge
```

実通信テストでは Query、全 Control、Events、切断後の復旧、権限エラーと C# サンプルの一致を検証します。
画像なしの Run に加え、公式 TestHost の `--with-icons` オプションで生成した決定的な PNG を取得します。
ゲームと Segment の PNG bytes・Segment 順・画像なしの `None` を確認し、実際に受信した JSON の
UTF-8 バイト数が 64KiB を超えることと、取得後も同じ RPC 接続で Query・Control が成功することを検証します。
Schema・fixture は sdist のみに含め、wheel は型付き client と runtime 依存だけを配布します。
