# 分離解析と実行統計 v0.2

## 保存先と権限

実行ホストのホーム配下 `~/agent-analysis-results/<project-id>/<case-id>/<stage>/<run-id>/` にUTF-8で保存する。project-idは対象root名と絶対パスの短いハッシュで区別する。`--output-root`で保存ルートのみ変更できる（`--project`は解析対象のまま）。startが表示する絶対runパスを採用し、リモート／コンテナではその実行環境のホームになる。
各runはinput.json（入力スナップショット）、record.json（時刻・状態・統計）、report.txt（結果）を持つ。source完了後の読者向けHTMLは別途report.html、図と条件表の入力はvisuals.json、生成物の対応関係はpresentation.jsonに保存する。
上書きしない。再解析は新run。途中停止はrunningのまま残り、未完了と分かる。
公開リポジトリに結果をcommitしない。旧来の対象プロジェクト内`local-results/`は移動・削除しない。保存ルートは本人のみの0700、runファイルは0600で作成する（既存の共有権限ルートは拒否）。
親にレポート保存用edit/executeを許可するが、原本変更は禁止。ホストでは入力read-only、結果ディレクトリのみwrite可能にすることを推奨。ホーム下への書き込みをホストで許す必要がある。
このファイルやtool一覧自体はパス単位のsandboxではない。許可ツールを増やした点はv0.1からの変更。

## ステップ

### source

入力: source_root（絶対ディレクトリ）、source_commit、dirty_state、build_config、scope、domain（driver/yocto/mw）、kit_revision、host_version。driver/MWのscopeには索引rootからの相対パス配列`resolved_files`を含める。
dirtyなら差分をハッシュで識別する。kernel/vendor版、MACHINE/DISTRO、生成ヘッダ等はbuild_configに記載する。
仕様本文・仕様解析結果は読まない。関数・登録・状態・資源・エラー・終了・非同期経路を領域Skillで分析する。
source runを開始した親Agentが、対象rootを絶対パスで確定し、git commit/dirty差分・解析範囲と対象rootが一致するか確認する。その後、管理者が事前に導入した`@colbymchenry/codegraph` **1.6.2**の実行ファイルを指定して`python3 agent-kit/prepare_codegraph.py --run <source-run絶対パス> --codegraph-bin <実行ファイル絶対パス>`を実行する。PATHの同名CLIは使わない。CLI導入、`codegraph install`、自動更新・ダウンロードは行わない。
索引は`CODEGRAPH_DIR=.codegraph-colbymchenry`を設定した`<source_root>/.codegraph-colbymchenry/codegraph.db`に限定する。別実装の既存`<source_root>/.codegraph/`は**調査・変更・削除・移動しない**。別名索引のDBがなくディレクトリも不存在／空の場合だけ、`codegraph init <source_root> --yes`を**一度だけ**実行する。この初回初期化は本依頼で許可された例外。初期化により別名ディレクトリ内へ`.gitignore`等が作成され得る。初期化前後のGit差分を確認し、索引や生成した`.gitignore`を公開リポジトリへ追加しない。Git除外の設定変更は自動実行しない。
別名索引に既存DBがあればinitしない。別名ディレクトリが非空なのにDBがない、シンボリックリンクがある、DBが破損・古い、対象root・版・構成に不一致がある場合はblocked。`sync`/再索引・削除・置換は自動実行しない。旧版・別実装のDBを「移行」するのではなく併存させる。
準備処理は1.6.2の`status <root> --json`を確認する（この版は`--strict`と`init --local-only`に非対応）。CLI版、索引root・索引先、index state、抽出エンジン版、未解決参照、未反映変更、worktree不一致、DB整合性、driver/MW対象ファイルのDB内容ハッシュを検査し、`codegraph-preparation.json`に結果を保存する。これは後続版の`--strict`と同一の検証ではない。対象外の解析カバレッジや意味的な正しさは保証しない。blockedなら理由をreport.txtと統計に記録して終了する。対象commit/dirty状態/構成の意味的整合は親Agentが別途確認する。
照会は準備記録の`cli_bin`を使い、すべてのCLIプロセスへ`CODEGRAPH_DIR=.codegraph-colbymchenry`と`CODEGRAPH_TELEMETRY=0`を渡す。MCPを使う場合も**同じCLI・環境変数・索引root**を設定し、その接続先が準備記録のDBに一致することを確認する。`codegraph explore <質問>`、`query`、`callers`、`callees`、`impact`等を使い、既定の別索引へ切り替わらないようにする。
CodeGraphの版、DB絶対パス、索引rootと版、status、実際の照会と結果を作業用テキストに残す。finishがそのテキストをrun内のcodegraph.txtへ固定する。原ソースで重要な辺を確認する。
初期化後もDBがない・未索引・古い索引・対象不一致・照会不能ならblocked。ユーザーが代替を承認した場合でも通常source完了とは別扱いにする。
Yoctoの.bb/.bbappend等はCodeGraphが意味を完全解決できると仮定しない。対応範囲を明記し、BitBakeメタデータと提供済み展開結果で補う。
結果: 対象と版、CodeGraph証拠、入口とシナリオ、資源・状態・依存、観測／推論／不明、未探索範囲。仕様との一致は判定しない。driverは特徴カードと条件別分岐を先頭に置き、比較していない項目を「独自」と断定しない。driverの詳しい表示・図・HTML契約は`agent-kit/reporting.md`を参照。

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
表示されたrunパスを成果物の保存先とする。作業用draftとusageはrun外に置く。sourceでは`python3 agent-kit/prepare_codegraph.py --run <run-dir> --codegraph-bin <管理者導入済みCLI絶対パス>`を先に一度実行する。最終報告のdraft.txtをfinishへ渡す。
`python3 agent-kit/run.py finish --run <run-dir> --report <draft.txt> --status completed --usage <usage.json>`
失敗／保留もfailed/blockedでfinishし、理由をレポートへ保存する。途中で落ちたrunを完了扱いにしない。
source成功時のみ `--codegraph-evidence <ローカルDBのstatus・照会履歴を含むテキスト>` も渡す。これは証拠ファイルの存在を検査するだけでDBや照会の真正性を自動保証しない。
記録ツールはLLMやCodeGraphを起動せず、Agent／ユーザーが実行する。自動テレメトリ収集フックではない。

source完了後、親Agentは根拠を確認したシーケンス・条件別分岐・特徴カードをrun外のvisuals入力JSONに用意する。`python3 tools/render_source_report.py --run <run-dir> --visuals <run外のvisuals-input.json>`でオフラインHTMLと検証用manifestを生成する。HTML生成は既存report/recordを書き換えない。対象のファイル・条件・実行文脈が不明なら図示で補完せず「不明」と示す。HTMLの完成状態はsource解析の成否とは区別して報告する。
配布用には`python3 tools/export_run.py --run <run-dir> --output <新しいZIP絶対パス>`を使う。これは作業draftを外し、`reader/`・`evidence/`・`execution/`へ分類して同一バイト列を一本化し、bundle-manifest.jsonで元のパスと別名を示す。既存runのファイルは削除しない。元レポートが旧ファイル名を参照する場合はmanifestを合わせて読む。

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
