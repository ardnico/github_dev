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
ツール許可はパス制限ではない。実際のホスト権限で原資料を読み取り専用にし、私有の結果保存先とsource初回のCodeGraph索引作成先だけを必要な範囲で書き込み可能にする。

## Codex CLIで使う

1. 対象プロジェクトのルートでCodexを起動する。解析結果は実行環境の`~/agent-analysis-results/`へ保存する。sourceは原資料を変更しないが、workflowに記載したCodeGraphの初回ローカル索引作成は`.codegraph/`等へ書き込む場合がある。
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
通常の依頼では利用者が細かい管理項目を埋める必要はない。ソース、使う仕様書（任意）、分かる範囲の対象版だけを指定する。原資料を書き換える依頼ではない。

| ステップ | 利用者が指定する情報 | Agentが調べて記録する情報／成果物 |
| --- | --- | --- |
| source | ソースroot（省略時は現在のworkspace）、対象版情報 | commit、dirty差分SHA-256、build条件、領域・範囲、kit/host/CodeGraph情報を自動収集。driverは案内ページと7つの観点別資料を出力 |
| spec | 仕様資料のパス、分かる範囲の対象版 | 文書ID・改訂・ハッシュ・範囲を抽出し、要求ID・節／ページ、入出力・例外・曖昧さ・欠落を記録 |
| compare | 仕様書を使った照合依頼（必要なsource/spec runをAgentが選ぶ） | 適用版を確認し、一致・不一致・実装未発見・文書化なし・不明の対応表を記録 |
| other | 保守・テスト・相談等のタスク | 対象、kit/host版を自動記録し、作業結果・検証・残課題を出力 |

対象版が分からない場合は「不明」と残し、必要性がなければ聞き返さない。scope・domain・案件ID・kit revision・host version・CodeGraph状態も自動導出し、文書や依存レポートのハッシュは記録ツールが固定する。

### ドライバ解析の依頼形式

```text
analysis-managerとしてドライバの仕組みを解析してください。
ソース: <絶対パス。省略時はこのworkspace>
仕様資料（任意）: <絶対パスの一覧または「なし」>
対象版: <kernel/vendor、driver/product、board、build情報のうち分かるもの。未知は「不明」でよい>
仕様書を使う照合も必要なら、その旨を書いてください。
```

ソース解析では仕様書の内容を読み込まない。照合が依頼された場合は、仕様専用runを独立して作成し、その完了結果とsource成果物だけでcompareを行う。commitや索引情報などの管理項目はAgentが調べる。

### 仕様書を使った照合

source/spec/compareの分離と入力制限を保つ。spec runは仕様書だけ、source runはソースだけ、compare runは両方の完了レポートだけを使う。照合の追加依頼があれば、同じ案件IDと保存済みrunから依存関係を選び、版・構成が合わない場合は保留する。

### 4. その他の処理のプロンプト

```text
<agent-maintainer|sherlock-emperor>としてotherステップを実行してください。
対象プロジェクト: <省略時は現在のworkspace>
task: <依頼内容と変更許可範囲>
workflow.mdに従い開始・終了・結果・統計を記録してください。
許可されていない変更、インストール、外部送信はしないでください。
```

### 保存・記録コマンド

デフォルト保存先は実行環境のホームにある`~/agent-analysis-results/<project-id>/<case-id>/<source|spec|compare|other>/<run-id>/`。
`--project`は解析対象、`--output-root`は保存先の任意指定。startが表示する絶対パスを使う。
コンテナ／リモート実行ではその環境のホームであり、手元PCのホームとは限らない。
project-idは対象root名とパスハッシュ。保存ルートは0700、runファイルは0600。旧`local-results/`は移動・削除しない。
UTF-8の`report.txt`、`input.json`、`start.json`、`record.json`を保存する。
source成功時はDB状態と照会履歴を記した`codegraph.txt`も保存。driver sourceでは`perspectives/`以下の7文書も保存し、record.jsonが各ハッシュを固定する。再実行は新runで、上書きしない。
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
# driver sourceの成功時はさらに --perspectives-dir /absolute/perspective-drafts を追加
# sourceではstartの直後に python3 agent-kit/prepare_codegraph.py --run /absolute/run を実行
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
非同期経路・資源寿命・要確認事項へ進む。`report.txt`は案内ページで、7つの観点別Markdown文書に詳細とMermaid図を分けて記載し、各図からE-01形式の証拠索引で原ソースへ戻れるようにする。
詳細は[reporting.md](agent-kit/reporting.md)。すべての関数を同じ長さで書かず、
公開入口、open失敗、IRQからNAPI/workerへの移行、close/removeの停止順を優先する。

### CodeGraphの初期化（sourceでDBがない場合はAgentが実行）

意図するCodeGraphは[このローカル索引型の実装](https://github.com/colbymchenry/codegraph)。
`@lzehrung/codegraph`等にも同名CLIがあり、バージョン3.1.3の`schemaVersion`/`manifestPath`形式は**別実装**。
`initialized: false`はそちらのmanifest未作成を指し、`.codegraph/codegraph.db`の有無を判定していない。
別実装の`init`/`sync`を既存の`.codegraph/`へ実行しない。まず`type -a codegraph`と
`readlink -f "$(command -v codegraph)"`等で実行ファイルを特定し、対象実装のCLIを選び直す。
`codegraph init`でソースを解析し、対象内の`.codegraph/codegraph.db`（SQLite）に
シンボル・呼び出し・依存関係を記録する。AgentはDBをCLIまたはローカルMCP経由で照会する。
MCPだけを接続してもDBはできない。`codegraph install`はAgent接続の設定であり、索引作成とは別。

```sh
codegraph version
codegraph telemetry off              # 社内規則に応じて設定を確認
codegraph init /absolute/project --local-only  # DB不在かつ未初期化の対象だけ。ローカルDBを作成しGit対象外へ
codegraph status /absolute/project --json --strict
cd /absolute/project
codegraph explore '対象APIの入口から終了までの呼び出し経路'
```

解析Agentが対象root・既存データを確認してから実行する。`codegraph install`やCLI導入は自動で行わない。索引の
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
