# 分離解析と実行統計 v0.2

## 保存先と権限

対象プロジェクトの `local-results/<case-id>/<stage>/<run-id>/` にUTF-8で保存する。
各runはinput.json（入力スナップショット）、record.json（時刻・状態・統計）、report.txt（結果）を持つ。
上書きしない。再解析は新run。途中停止はrunningのまま残り、未完了と分かる。
公開リポジトリに結果をcommitしない。導入先でもlocal-results/をignoreする（install.pyは既存.gitignoreを変更しない）。
親にレポート保存用edit/executeを許可するが、原本変更は禁止。ホストでは入力read-only、結果ディレクトリのみwrite可能にすることを推奨。
このファイルやtool一覧自体はパス単位のsandboxではない。許可ツールを増やした点はv0.1からの変更。

## ステップ

### source

入力: source_root、source_commit、dirty_state、build_config、scope、domain（driver/yocto/mw）、kit_revision、host_version。
dirtyなら差分をハッシュで識別する。kernel/vendor版、MACHINE/DISTRO、生成ヘッダ等はbuild_configに記載する。
仕様本文・仕様解析結果は読まない。関数・登録・状態・資源・エラー・終了・非同期経路を領域Skillで分析する。
CodeGraphのバージョン、索引の対象root/commit/dirty状態/構成、queryと結果の出典を記録する。
`codegraph_explore`を実行し、その応答を作業ファイルへ保存する。finishがrun内のcodegraph.txtへ固定する。根拠の確認に原ソースを併用する。
未接続、未索引、古い索引、対象不一致はblocked。ユーザーが代替を承認した場合でも通常source完了とは別扱いにする。
Yoctoの.bb/.bbappend等はCodeGraphが意味を完全解決できると仮定しない。対応範囲を明記し、BitBakeメタデータと提供済み展開結果で補う。
結果: 対象と版、CodeGraph証拠、入口とシナリオ、資源・状態・依存、観測／推論／不明、未探索範囲。仕様との一致は判定しない。

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
CodeGraphの初期化／索引更新は別の明示許可で実施し、その処理自体もotherとして記録する。

## 共通実行方法

開始直前に `python3 agent-kit/run.py start --project <対象root> --case <案件ID> --stage <source|spec|compare|other> --input <入力JSON>` を実行。
出力されたrunディレクトリ内で作業する。最終報告をdraft.txtとして保存し、終了時にfinishへ渡す。
`python3 agent-kit/run.py finish --run <run-dir> --report <draft.txt> --status completed --usage <usage.json>`
失敗／保留もfailed/blockedでfinishし、理由をレポートへ保存する。途中で落ちたrunを完了扱いにしない。
source成功時のみ `--codegraph-evidence <応答保存ファイル>` も渡す。これは証拠の存在を検査するだけで実ツール実行を保証しない。
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
