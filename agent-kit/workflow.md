# 分離解析と実行統計 v0.2

## 保存先と権限

実行ホストのホーム配下 `~/agent-analysis-results/<project-id>/<case-id>/<stage>/<run-id>/` にUTF-8で保存する。project-idは対象root名と絶対パスの短いハッシュで区別する。`--output-root`で保存ルートのみ変更できる（`--project`は解析対象のまま）。startが表示する絶対runパスを採用し、リモート／コンテナではその実行環境のホームになる。
各runはinput.json（入力スナップショット）、record.json（時刻・状態・統計）、report.txt（結果）を持つ。完了したdriver source runは`perspectives/`に観点別Markdown資料を持ち、その各SHA-256をrecord.jsonへ記録する。compareはreport.txtに加えて観点別資料のハッシュも検証する。
上書きしない。再解析は新run。途中停止はrunningのまま残り、未完了と分かる。
公開リポジトリに結果をcommitしない。旧来の対象プロジェクト内`local-results/`は移動・削除しない。保存ルートは本人のみの0700、runファイルは0600で作成する（既存の共有権限ルートは拒否）。
親にレポート保存用edit/executeを許可するが、原本変更は禁止。ホストでは入力read-only、結果ディレクトリのみwrite可能にすることを推奨。ホーム下への書き込みをホストで許す必要がある。
このファイルやtool一覧自体はパス単位のsandboxではない。許可ツールを増やした点はv0.1からの変更。

## ステップ

### source

利用者が指定するもの: ソースの絶対パス（省略時は現在の作業root）、必要なら仕様書などのファイルパス、分かる範囲の対象版情報（kernel/vendor、driver/product、board、MACHINE/DISTRO等）。対象版を特定できない場合は「不明」と記録し、必須入力として聞き返さない。
run入力: source_root、source_commit、dirty_state、build_config、scope、domain（driver/yocto/mw）、kit_revision、host_version。source_commitとdirty状態・差分SHA-256はGitから、build_configは対象repoの設定と利用者が示した版情報から、scopeとdomainは依頼およびソースから導出する。case-idはAgentが一意に選ぶ。取得できないkit/host/CodeGraph情報は理由付きで不明として残す。
dirtyなら差分をハッシュで識別する。kernel/vendor版、MACHINE/DISTRO、生成ヘッダ等はbuild_configに記載する。
source runでは仕様本文・仕様解析結果は読まない。仕様書パスも同じ依頼で指定できるが、ファイルを開くのはspec runだけにする。仕様書を使った照合が依頼に含まれる場合、spec runへ仕様書だけ、compare runへ完了したsource/spec成果物だけを渡す。関数・登録・状態・資源・エラー・終了・非同期経路を領域Skillで分析する。
source runを開始した親Agentが、対象rootを絶対パスで確定し、git commit/dirty差分・解析範囲と対象rootが一致するか確認する。その後 `python3 agent-kit/prepare_codegraph.py --run <source-run絶対パス>` を実行する。使用対象は`@colbymchenry/codegraph`であり、同名の別実装を実行しない。スクリプトは`status --json`の応答形式から実装とrootを確認してから、`<source_root>/.codegraph/codegraph.db`がない場合だけ、`.codegraph/`が存在しないか空であれば`codegraph init <source_root> --local-only`を**一度だけ**実行する。PATHで別実装が選ばれる場合は承認済みの正しい実行ファイルを`--codegraph-bin <絶対パス>`で指定する。本依頼はこの「DB不在時の初期化」を許可している。`--local-only`は対象のローカルGit除外設定等へ書き込む可能性があるため実行前後の差分を確認する。CLI導入や`codegraph install`、外部からの自動ダウンロードは別の許可が必要。
既存DBがあればinitを実行しない。`.codegraph/`が空でないのにDBがない、シンボリックリンク／別の索引がある、または既存DBが破損している場合も勝手に削除・上書き・強制再索引せずblockedとする。
初期化の有無、時刻・コマンド・終了コード・出力と版はsource runの`codegraph-preparation.json`へ保存される。別実装の`3.1.3`/`manifestPath`形式が返った場合、DBを削除・再初期化せず、同名CLI衝突としてblockedにする。スクリプトがblockedなら理由をreport.txtと統計に記録してblockedで終了する。スクリプトはDBと、対象実装に対応する`status --json --strict`を確認するが、実際の照会と対象commit/dirty状態/構成の意味的整合は親Agentが確認する。既存DBの不整合・古い索引の`sync`/再索引は自動実行せず、必要性を報告して確認を求める。自動同期を盲信しない。
照会は対象rootで`codegraph explore <質問>`、`query`、`callers`、`callees`、`impact`等のCLI、または同じローカルDBを参照するMCPを用いる。実行時の作業rootを明示し、違うDBを参照しない。
CodeGraphの版、DB絶対パス、索引rootと版、status、実際の照会と結果を作業用テキストに残す。finishがそのテキストをrun内のcodegraph.txtへ固定する。原ソースで重要な辺を確認する。
初期化後もDBがない・未索引・古い索引・対象不一致・照会不能ならblocked。ユーザーが代替を承認した場合でも通常source完了とは別扱いにする。
Yoctoの.bb/.bbappend等はCodeGraphが意味を完全解決できると仮定しない。対応範囲を明記し、BitBakeメタデータと提供済み展開結果で補う。
結果: 対象と版、CodeGraph証拠、入口とシナリオ、資源・状態・依存、観測／推論／不明、未探索範囲。仕様との一致は判定しない。
driverで完了するsource runは`report.txt`を短い索引とし、以下7資料を`perspectives/`に保存する。欠けた視点を黙って省かず、該当機能がない／未探索のどちらか、根拠とともに記す。Mermaidのシーケンス図・状態図・flowchartを用い、ノード・矢印に根拠IDを付ける。詳しい表示契約は`agent-kit/reporting.md`を参照。

- `00-overview.md`: 対象・版、読み方、構成と主要経路の全体図。
- `01-registration-interfaces.md`: 登録、ID対応、実際に公開された操作と到達経路。
- `02-data-and-state.md`: 中心構造体・ヘッダ・所有関係・状態遷移・同期primitive。
- `03-scenarios.md`: probe成功／失敗、公開操作、TX/RXなどの順序・分岐・戻り値。
- `04-irq-and-async.md`: hard IRQ/threaded IRQ/NAPI/work等の実在する非同期境界、共有状態と再投入。
- `05-resources-and-lifecycle.md`: 取得・利用・停止・同期・解放を失敗経路とremove/shutdown/PMに結ぶ。
- `06-open-questions-and-evidence.md`: 優先度付き要確認事項、探索範囲、E-01形式の証拠索引。

### spec

入力: spec_id、spec_revision、spec_files（絶対パス）、scope、domain、kit_revision、host_version。
ファイルごとのSHA-256を取得する。改訂日、承認状態、対象製品版、適用構成も入力に示す。
仕様原本だけを読み、要求ID、節／ページ、前提、入力、処理、出力、例外、タイミング、曖昧さ・矛盾を抽出する。
ソース・source結果は読まない。書いていない仕様を実装や一般常識から追加しない。
PDF/Word等の抽出で表・図・OCRが不明ならその位置を記録する。根拠を抽出テキストだけでなく原本の節／ページへ戻せるようにする。
結果: 版と文書ハッシュ、要求一覧、用語、適用条件、曖昧さ、欠落、未読範囲。実装との一致は判定しない。

### compare

入力: source_run、spec_run（完了runの絶対パス）、scope、domain、kit_revision、host_version。
同じ案件の完了source/specだけ使う。run.pyがレポートと入力のハッシュを検証し依存版を固定する。
適用製品版・構成の整合はAgentが明示確認する（スクリプトは意味を判定できない）。
不一致または適合不明ならblockedとして理由を保存し、一致判定へ進まない。
仕様照合Skillで双方向にmatch/mismatch/implementation-not-found/undocumented/unknownを整理する。
結果: 両run IDと版、照合表、根拠、不明、確認優先度。原資料の追加解析が必要なら新runとして戻す。

### other

保守、相談、テスト、索引作成等も入力task、scope、kit_revision、host_versionを指定して実行を記録する。
sourceに必要な**DB不在時の初回初期化**はsource run内で記録する。CLI導入、既存DBの同期／再索引、他の用途の索引作成は別の明示許可とother記録を要する。

## 共通実行方法

開始直前に `python3 agent-kit/run.py start --project <対象root> --case <案件ID> --stage <source|spec|compare|other> --input <入力JSON> [--output-root <私有の保存root>]` を実行。
出力されたrunディレクトリ内で作業する。sourceでは`python3 agent-kit/prepare_codegraph.py --run <run-dir>`を先に一度実行する。最終報告をdraft.txt、driverの7資料を別の一時ディレクトリに作り、終了時にfinishへ渡す。資料はreport.txtの参照先と一致させ、run.pyにコピーさせる。
`python3 agent-kit/run.py finish --run <run-dir> --report <draft.txt> --status completed --usage <usage.json>`
driver source成功時はさらに`--perspectives-dir <7つのMarkdown資料を入れたディレクトリ>`を渡す。ツールは必要なファイル名、非空UTF-8、各ファイルSHA-256を検証・保存する。
失敗／保留もfailed/blockedでfinishし、理由をレポートへ保存する。途中で落ちたrunを完了扱いにしない。
source成功時のみ `--codegraph-evidence <ローカルDBのstatus・照会履歴を含むテキスト>` も渡す。これは証拠ファイルの存在を検査するだけでDBや照会の真正性を自動保証しない。
記録ツールはLLMやCodeGraphを起動せず、Agent／ユーザーが実行する。自動テレメトリ収集フックではない。

## 統計

usage.jsonは `{"coverage":"partial", "missing_reason":"ホストが未公開", "events":[]}` から開始できる。
coverageはcomplete/partial/unavailable。空eventsを0クレジットと解釈しない。
呼び出し単位でevent_id、parent_event_id、agent、requested_model、actual_model、started_at、ended_at、
input_tokens、output_tokens、cached_input_tokens、reasoning_tokens、credits、rate、evidence_source、missing_reasonを記録する。
時刻はタイムゾーン付きISO 8601。run.pyがステップ開始・終了時刻と経過秒を記録する。
actual_modelは実測値。Fusionの内部モデルが不明ならnull。子や再試行の各呼び出しを別eventにする。
イベントはcall単位のみ。セッション集計と子の値を重複投入しない。部分データの合計を総消費と表示しない。
トークンは実際の使用量。context上限／モデル能力とは別。cached/reasoningは内数かどうかをevidence_sourceに示し、単純加算しない。
creditsは実測の請求クレジット。通貨額・トークンから換算した見積もりと混ぜない。
rateは単価スナップショット: currency/unit、input/output/cached_input単価、credit_multiplier、discount、effective_at、checked_at、source。
プラン・ホスト・モデルごとに取得し、過去の割引を恒久値として埋め込まない。トークン毎秒を測る場合は別のthroughput項目にする。
各不明値はnull、missing_reasonに理由を記す。実測0は証拠があるときだけ。料金を推測で補完しない。
UI／API／承認済みトレースから取得した値をusage.jsonへ正規化する。現時点でホスト別自動インポーターはない。
完了後に使用量が判明した場合、`run.py usage --run ... --input usage.json`で追記する。元記録は変えずrevisionを増やす。
集計するときは各runの最新usage revisionを採用し、元recordとの二重加算をしない。
