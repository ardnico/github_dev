# github_dev — Agent Kit v0.2

Copilot / Codex向けの、根拠を残して育てるAgentキット。
初版は調査・仕様照合を中心にし、保守と汎用のシャーロック皇帝を備える。
実際の製品クライアントによる受入試験は未実施。構文・生成整合性・Pythonテストと、独立した指示評価を区別する。

## 選択する親と呼び出される子

| ID | 役割 | 利用者から選択 |
| --- | --- | --- |
| analysis-manager | 調査・仕様照合 | する |
| agent-maintainer | Agent保守 | する |
| sherlock-emperor | シャーロック皇帝（汎用参謀） | する |
| evidence-researcher | 根拠収集 | 親から委任 |
| evidence-reviewer | 独立レビュー | 親から委任 |

専門手順はドライバ、OS/Yoctoレシピ、MW、仕様照合の4 Skills。
設計／製作専用Agent、自動モデル選択、常駐監視、無制限の再委任は初版に含めない。
シャーロック皇帝は相談にも明示的な作業依頼にも使えるが、全自動の製作工程を保証しない。

## Copilotで使う

1. このリポジトリをcloneしてVS Codeで開く。Copilot harnessを選ぶ。
2. Agent Customizationsで親3種とSkillsを確認する。Agent一覧のIDと上の表を対応させる。
3. モデル選択欄で、利用可能ならFusionを選ぶ。モデルを定義に固定していないためホスト設定を利用する。
4. `analysis-manager`を選び、下記のステップ別プロンプトで依頼する。
5. 子の実行時モデル、ツール、返却結果をUIで確認する。子へのFusion継承は未検証。

Copilot向け定義は`.github/agents/`、Skillsは`.github/skills/`。
`agents`や`handoffs`等のLocal専用設定は生成しない。Fusionはモデル実行の仕組みであり、子の起動機構ではない。
解析親には結果・統計の保存のためedit/executeを公開する。子は原資料を編集しない。
ツール許可はパス制限ではない。原資料はread-only、local-resultsだけ書き込み可能な環境を推奨する。

## Codex CLIで使う

1. 対象プロジェクトのルートでCodexを起動する。原資料の変更は禁止し、local-resultsへの保存だけ許可する。
2. 次のいずれかを依頼する（本キットのAGENTS.mdが親ロールへ案内する）。
   - `調査・仕様照合として、この範囲を調べて。変更しないで。`
   - `Agent保守として、このキットの問題を診断して。まず修正案まで。`
   - `シャーロック皇帝として、目的と制約を整理して次の一手を提案して。`
3. 子2種は`.codex/agents/*.toml`から利用する。Skillsの正本は`.agents/skills/`。

CodexにCopilotと同じ親Agent選択UIがあるとは仮定しない。親は現在のセッションが役割本文を読み、子のみTOML定義を使う。
子のsandbox/承認/MCPは親を継承する。プロンプトの「変更禁止」はセキュリティ境界ではない。
子のshellは無効化するが、MCP等の書き込み権限は親ホストでも制限する。

## 別の対象プロジェクトへコピー

Python 3.11以上、外部Python依存なし。既存ファイルは上書きしない。

```sh
python3 tools/install.py --target /absolute/path/to/target-project
python3 tools/install.py --target /absolute/path/to/target-project --apply
```

対象フォルダは事前に用意する。競合があるとコピー前に停止する。
既存AGENTS.md等がある場合は手動で差分を統合する。機密ソースをこの公開リポジトリへコピーしない。
インストールはローカルファイル配置だけで、commit、MCP導入、モデル契約は行わない。
保守作業はこの管理元リポジトリで行い、生成済み定義を対象へ再適用する。導入先ではtools/tests/docsは配布しない。

## ステップ別の依頼と成果物

source → spec → compareを**独立した実行**にする。sourceとspecの順序は入れ替え可能。
別セッション、または入力を限定した子に分離し、前段の結論を次段に混入させない。
各依頼で`agent-kit/workflow.md`を読み、開始記録→解析→結果保存→終了記録を行う。
以下の`<...>`は実値へ置換する。原資料を書き換える依頼ではない。

| ステップ | 入力・版情報 | 出力の内容 |
| --- | --- | --- |
| source | ソース絶対パス、commit、dirty差分ハッシュ、ビルド構成、範囲、領域、CodeGraph版・ローカルDB状態 | 実装の入口・経路・状態・資源・根拠・未探索範囲 |
| spec | 文書絶対パス、文書ID・改訂、承認状態、適用製品版・構成、範囲 | 要求ID・節／ページ、入出力・例外・曖昧さ・欠落 |
| compare | 完了したsource/specのrun絶対パス、適用版・構成の整合 | 一致・不一致・実装未発見・文書化なし・不明の対応表 |
| other | 保守・テスト・相談等のタスク、対象、条件 | 作業結果・検証・残課題 |

共通で案件ID、キットcommit、実行ホスト名・版を明示する。文書ハッシュと依存レポートのハッシュは記録ツールが固定する。

### 1. ソース解析のプロンプト

```text
analysis-managerとしてsourceステップだけを実行してください。
対象プロジェクト: <絶対パス> / 案件ID: <case-id>
source_root: <絶対パス> / source_commit: <SHA>
dirty_state: <clean、または差分とそのSHA-256>
build_config: <kernel/vendor版・設定、またはMACHINE/DISTRO等>
domain: <driver|yocto|mw> / scope: <対象と除外範囲>
kit_revision: <キットSHA> / host_version: <製品名と版>
CodeGraph: <導入版、.codegraph/codegraph.dbの絶対パス、索引root・対象版・構成>
workflow.mdに従い入力JSONを作成してstartを実行する。
仕様書と仕様解析結果は読まない。対象プロジェクトのローカルDBの存在と
codegraph status --json --strictを確認する。照会は対象rootでCodeGraph CLI
（explore/query/callers/callees等）または同じDBに接続したMCPで行い、
status、照会コマンド/質問、結果を保存して原ソースで根拠を確認する。
DB未作成・未索引・古い索引・対象不一致ならblocked。索引更新は別途許可を得る。
driverはreporting.mdに従い、登録・関連構造体/ヘッダ・公開操作（open/close/ioctl等）・
hard IRQ/threaded IRQ/NAPI/work・probe/remove/失敗経路・資源寿命を区別して報告する。
存在しない操作やIRQスレッドは創作せず、登録表と原ソースで有無を示す。
MWは公開API・初期化終了・
データ経路・非同期・障害復旧、yoctoはレシピ・依存・構成・タスクを優先する。
レシピ意味論などグラフの未対応範囲は明示し、必要な展開結果を別途要求する。
report.txtと統計を所定runへ保存する。次のステップは開始しない。
```

### 2. 仕様書解析のプロンプト

```text
analysis-managerとしてspecステップだけを実行してください。
対象プロジェクト: <絶対パス> / 案件ID: <case-id>
spec_id: <文書ID> / spec_revision: <改訂番号・改訂日>
spec_files: [<原本の絶対パス>]
承認状態・適用製品版・構成: <値。不明なら不明と明示>
domain: <driver|yocto|mw> / scope: <対象章と除外範囲>
kit_revision: <キットSHA> / host_version: <製品名と版>
workflow.mdに従い入力JSONを作成してstartを実行する。
ソースとsource解析結果は読まない。要求ID、節／ページ、前提、入力、処理、
出力、例外、タイミングを抽出し、曖昧さ・矛盾・不足・未読の図表を区別する。
存在しないプログラム仕様を推測で補わない。report.txtと統計を所定runへ保存する。
次のステップは開始しない。
```

### 3. 照合のプロンプト

```text
analysis-managerとしてcompareステップだけを実行してください。
対象プロジェクト: <絶対パス> / 案件ID: <case-id>
source_run: <完了source runの絶対パス>
spec_run: <完了spec runの絶対パス>
domain: <driver|yocto|mw> / scope: <照合範囲>
kit_revision: <キットSHA> / host_version: <製品名と版>
workflow.mdに従い入力JSONを作成しstartで依存runを検証する。
対象版・構成の適合を確認し、不一致なら照合を保留する。
両レポートを双方向で照合する。未発見と不存在、未文書化と実装不良を混同しない。
追加の原資料解析は別source/spec runとして提案し、その場で混ぜない。
対応表・根拠・不明・確認優先度をreport.txtへ、統計をrecord.jsonへ保存する。
```

### 4. その他の処理のプロンプト

```text
<agent-maintainer|sherlock-emperor>としてotherステップを実行してください。
対象プロジェクト: <絶対パス> / 案件ID: <case-id>
task: <依頼内容と変更許可範囲> / scope: <対象と除外>
kit_revision: <キットSHA> / host_version: <製品名と版>
workflow.mdに従い開始・終了・結果・統計を記録してください。
許可されていない変更、インストール、外部送信はしないでください。
```

### 保存・記録コマンド

デフォルト保存先は実行環境のホームにある`~/agent-analysis-results/<project-id>/<case-id>/<source|spec|compare|other>/<run-id>/`。
`--project`は解析対象、`--output-root`は保存先の任意指定。startが表示する絶対パスを使う。
コンテナ／リモート実行ではその環境のホームであり、手元PCのホームとは限らない。
project-idは対象root名とパスハッシュ。保存ルートは0700、runファイルは0600。旧`local-results/`は移動・削除しない。
UTF-8の`report.txt`、`input.json`、`start.json`、`record.json`を保存する。
source成功時はDB状態と照会履歴を記した`codegraph.txt`も保存。再実行は新runで、上書きしない。
途中終了はstart.jsonだけの未完了runとして残る。公開Gitには結果を追加しない。

例えばotherの入力JSONは次の形式（source/spec/compareの必須キーは上表とworkflow.md参照）。

```json
{"task":"Agent定義の点検","scope":"agent-kit","kit_revision":"<SHA>","host_version":"<製品名・版>"}
```

```sh
python3 agent-kit/run.py start --project /absolute/project --case case001 --stage other --input /absolute/input.json
# 任意の私有保存先にしたい場合、startへ --output-root /absolute/private-results を追加
# 表示されたrunパスを以下へ指定。draft.txtとusage.jsonは実行結果から作成する。
python3 agent-kit/run.py finish --run /absolute/run --report /absolute/draft.txt --status completed --usage /absolute/usage.json
# sourceの成功時は上のfinishに --codegraph-evidence /absolute/db-query-log.txt を追加
# 保留・失敗も --status blocked または failed で理由を保存
python3 agent-kit/run.py usage --run /absolute/run --input /absolute/later-usage.json
```

### 使用量・レートの扱い

開始／終了時刻・経過秒はスクリプトで記録する。モデル呼び出しごとに親子ID、Agent名、
要求モデル／実モデル、入力／出力／キャッシュ／推論トークン、消費クレジット、単価、
倍率・割引・適用日時・確認日時・出典を`usage.events`に残す。詳細形式は[workflow.md](agent-kit/workflow.md)。
ここでトークン量は**実消費量**。モデルのコンテキスト上限や推奨予算とは別の指標。

**ホスト別の使用量自動取得は未実装**。UI・API・承認済みログで取得できた値を記録し、
取得不能を0扱いしない。Fusionの実モデルが非公開ならnull。レートを推測で埋めない。
全項目取得不能の場合も以下で記録できる。

```json
{"coverage":"unavailable","missing_reason":"実行ホストが呼び出し別のモデル・使用量を公開しない","events":[]}
```

遅れて判明した使用量は`usage`コマンドで版を追加する。集計時は最新の版だけを採用し、
親の集計と子の使用量、キャッシュ／推論の内数を二重加算しない。
この記録ツール自体はモデルやCodeGraphを起動しない。プロンプトに従うAgentがツールを実行する構成。

### ドライバsourceレポートの読み方

冒頭の短い全体像から、公開インタフェース・関連構造体/ヘッダ・シナリオ別の処理順、
非同期経路・資源寿命・要確認事項へ進み、E-01形式の証拠索引で原ソースに戻れるようにする。
詳細は[reporting.md](agent-kit/reporting.md)。すべての関数を同じ長さで書かず、
公開入口、open失敗、IRQからNAPI/workerへの移行、close/removeの停止順を優先する。

### CodeGraphの準備（対象環境で承認後）

意図するCodeGraphは[このローカル索引型の実装](https://github.com/colbymchenry/codegraph)。
`codegraph init`でソースを解析し、対象内の`.codegraph/codegraph.db`（SQLite）に
シンボル・呼び出し・依存関係を記録する。AgentはDBをCLIまたはローカルMCP経由で照会する。
MCPだけを接続してもDBはできない。`codegraph install`はAgent接続の設定であり、索引作成とは別。

```sh
codegraph version
codegraph telemetry off              # 社内規則に応じて設定を確認
codegraph init /absolute/project --local-only  # 許可を得た対象だけ。ローカルDBを作成しGit対象外へ
codegraph status /absolute/project --json --strict
cd /absolute/project
codegraph explore '対象APIの入口から終了までの呼び出し経路'
```

このコマンド例は手順であり、本キットの導入処理が実行するものではない。索引の
commit・dirty差分・ビルド構成の適合は別途確認する。コードグラフは静的構造なので、
ドライバのIRQやYoctoレシピの実効構成まで自動的に証明できない。

## キットの保守と検証

```sh
python3 tools/render.py
python3 tools/validate.py
python3 -m unittest discover -s tests -v
```

- 正本: `agent-kit/roles/`、`agent-kit/common.md`、`.agents/skills/`
- 生成先: `.github/agents/`、`.codex/agents/`、`.github/skills/`
- モデル方針: `agent-kit/model-policy.json`（メタデータのみ。自動切替はしない）
- [設計とロードマップ](docs/architecture.md)
- [評価手順と合格基準](docs/evaluation.md)
- [互換性・MCP・公式資料](docs/compatibility.md)
- [初版の検証記録](docs/validation-status.md)

自動生成ファイルは直接編集しない。権限、基準、価格、モデルの変更を保守Agentに無断で任せない。
