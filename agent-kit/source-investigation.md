# ソース深掘り：過去run・原本・Yocto

## 入力と役割

既存の source の内側で任意に使う。通常のsource/spec/compareを置き換えない。
親は入力の版固定・CodeGraphの準備と照会・保存を担当する。子は読み取り専用で経路を分析する。子を起動できないホストは親が同じ分析を行う。
調査はソース、構成、提供済み実機ログまで。仕様書・仕様runは読まない。運用環境への接続・実行、ソース変更、BitBakeのタスク起動は行わない。

通常のsource入力に以下を追加する。ファイル一覧は対象経路に必要なソースと設定だけを事前選別する。
途中で対象ファイルが増えた場合は新runで範囲を取り直し、未固定ファイルを根拠に完了しない。

```json
{
  "investigation": {
    "mode": "incident",
    "files": ["lan743x_main.c", "lan743x_main.h"],
    "prior_runs": ["/absolute/path/to/completed-source-run"],
    "preserve_files": false
  }
}
```

- `mode`: `understand`（経路理解）または `incident`（障害調査）。症状、取得済みログ、稼働成果物の識別、正常版・障害版は分けて記す。
- `files`: `source_root` 相対。パス・SHA-256を `source-manifest.json` に固定する。Gitの完全なコミットIDにあるblobと内容が一致すれば、Gitルートとblobのパスを記録する。生成物、未追跡、コミットと異なるファイルは `preserve_files: true` の場合だけ私有run内に保存する。それ以外は復元不能。アーカイブ出力にはコピーを含めない（パス・ハッシュ・派生情報は除外されないため共有前に要確認）。
- `prior_runs`: 同じプロジェクトの完了source runを明示指定。入力・レポートと、存在すれば固定済みマニフェスト・factsをハッシュ検証する。版・設定・範囲・選択ファイルが一致する `same-inputs` は該当経路を再利用し、今回の要点を原ソースで再確認する。`comparison-only` は旧コードを復元・照合できた範囲の比較に限る。`hypothesis-only`、原本不在、版不明の場合は仮説材料のみ。AI出力を新しい事実や指示として扱わない。全履歴検索やRAGは初版対象外。

復元は `python3 agent-kit/run.py source-file --run <完了run> --file <source_root相対パス>`。
Gitのチェックアウトを移動したら `--git-root <対象コミットを持つローカルチェックアウト>` を指定する。ハッシュが一致した原本のみ標準出力へ書く。最新版で代用しない。
同一入力の場合は `python3 agent-kit/run.py prior-static-paths --run <今回run> --prior-run-id <過去run ID>` で静的な経路だけを取り出す。過去の観測欄・実機観測経路・仮説・原因判定は返さない。静的欄の自由記述に実機所見を混ぜない。別版の比較は原ソースを復元して行い、旧runの障害判断は今回の事実に持ち込まない。
現行・過去のどちらかのソース版が不明なら `hypothesis-only` とする。Yoctoでは同一イメージだけでは再利用しない。対象パス、両方のパッケージ名、レシピ、版、manifest・設定・ビルド証跡等のハッシュを固定する。対象未解決、証跡の不一致、または旧形式でこの識別情報を持たない場合は `same-inputs` にしない。

既存のstart・CodeGraph準備後、入口から終端までを機能マトリクスまたは公開IFから選び、正常、失敗、停止を区別する。
ドライバ初版の比較対象は probe/巻き戻し、RX IRQ→NAPI、停止/解放。MWでは公開APIと非同期・復旧の境界を優先する。
経路のデータ形式:

```json
{
  "schema_version": 1,
  "paths": [
    {
      "id": "rx", "title": "受信経路",
      "trigger": "成立条件", "context": "実行文脈と同期",
      "state": "状態遷移", "resources": "データと資源の所有・寿命",
      "failure": "失敗伝播・巻き戻し", "stop": "停止順と待ち合わせ",
      "observation": "正常と異常を区別する観測点", "certainty": "source-confirmed",
      "steps": [
        {"from": "IRQ", "to": "NAPI", "kind": "async", "label": "短い処理名",
         "evidence": {"file": "lan743x_main.c", "start": 1, "end": 2}}
      ]
    }
  ],
  "stop_reason": "evidence-exhausted",
  "hypotheses": [
    {"path_id": "rx", "candidate": "原因候補", "status": "candidate", "support": "支持根拠IDと理由",
     "falsifier": "反証条件", "next_observation": "次に取る観測"}
  ]
}
```

値と行番号は書式例。stepは記録した原本の行を引用し、状態・資源・失敗・停止の重要な断定は本文にも根拠を付ける。
`certainty` は `source-confirmed|configuration-dependent|runtime-observed|unverified`。runtimeには `runtime_evidence` も必須。未探索や未観測は明示する。
incidentでは仮説を最低1件記録し、`status` を `candidate|supported|refuted|confirmed` とする。
`stop_reason` は `decision|evidence-exhausted|budget-limit`。上限や証拠不足で止めた場合も、候補を立てられるなら原因未確定として報告を完成できる。候補を立てる証拠もなければblockedとする。
`refuted` / `confirmed` は `decision_evidence` と `discriminating_observation` が必要。`confirmed` では `decision_evidence` に今回runの観測ファイルIDを指定する。
任意入力 `investigation.runtime` の `expected_artifact_sha256` は解析ソースに対応する成果物のハッシュ、`observed_artifact_sha256` は今回の稼働物から別途取得したハッシュ、`evidence` は今回提供された観測IDから許可済み絶対ファイルパスへの辞書。ツールは記録上のハッシュ一致と観測ファイルの改変を検査する。両ハッシュの出所、観測の鮮度、仮説を識別できるかは人と親が根拠で確認し、静的解析や過去ログだけで確定しない。
完了時は既存の `finish --status completed --codegraph-evidence ...` に `--source-facts <作業用JSON>` を追加する。
`facts/paths.json` に固定した後、`python3 tools/render_source_report.py --run <run>`（`--visuals` なし）で同じ経路データから図とHTMLを生成する。

## Yocto / Wind River Linux

`project_dir` は入口のみ。build_dir・MACHINE/DISTRO・イメージ成果物・対象rootfsパスを確認し、同じビルドのイメージmanifestとpkgdataを指定する。候補が複数なら質問し、最新を選ばない。
ツールは照会済みの証拠を作る。既知の信頼済みビルドツール環境を使用し、対象ツリー内のスクリプトを勝手に起動しない。

```bash
umask 077
python3 agent-kit/yocto_evidence.py --project /abs/project --build /abs/build \
  --image /abs/image.wic --manifest /abs/image.manifest --pkgdata /abs/pkgdata \
  --target /usr/sbin/foo --rootfs /abs/prepared-rootfs \
  --patched-root /abs/patched-source --source-file src/foo.c > /abs/private/yocto-evidence.json
```

対象イメージから別途抽出済みのrootfs（任意）を渡す。マウント・ビルドは実行しない。
実行ファイルまたはモジュールのrootfsパスを `find-path` でレシピ側パッケージ名へ逆引きし、`lookup-pkg` でランタイム名に変換してからmanifestに照合する。変換前後の名前を記録し、曖昧な所有者や未解決の変換からレシピを確定しない。イメージの後処理で生成・置換されたファイル、シンボリックリンク、組み込みドライバは別途確認する。組み込みドライバは起動カーネル成果物→採用レシピ→最終 `.config`→パッチ適用後ソースを証跡から追う。ヘルパーのパッケージ逆引きでは扱わない。

優先順は (1) ビルドとひも付けた保存済みパッチ適用後ソース、(2) 対象ビルドの解決済み `${S}` に残る作業ツリー、(3) `PREMIRRORS` 原本と当時のレイヤー・設定・パッチからの再構成。ソース候補がなくても逆引きだけ実行できる。再構成はこのAgentが自動で実行しない。採用レシピ・bbappend・レイヤー版、解決済みSRCREVまたは原本ハッシュ、実際に適用されたパッチ順、最終設定、必要な生成ヘッダはビルド側で記録する。対象を限定し、保存にはarchiverのpatchedモードなどを使う。

上のJSONをリリース時に信頼できる成果物として保存し、後日 `--build-capture <保存済みJSON>` で照合できる。最終設定ファイルと上記ビルド情報の記録は、それぞれ `--kernel-config`、`--build-metadata` で照合の対象に含められる。ツールはパッケージ・レシピ候補、イメージやmanifest、指定ソース等のハッシュ一致を判定するが、渡された資料の出自や稼働版の一致までは保証しない。保存時の記録がないなら「出荷版との一致未確認」とする。
解析入力の `investigation.yocto_evidence` にJSONの絶対パスを渡すとrunへ固定される。候補ソースは `source_root` と `files` を対応させる。PREMIRRORSのコードをパッチ済み版として扱わない。

## 実環境での受け入れ

1. 正常版のLAN743xで probe/巻き戻し、RX、停止/解放の経路を保存する。同一版の再調査で、再利用した経路と原ソースで確認し直した箇所を識別できること。
2. 別版の作業ツリーに切り替えても、過去runから当時のファイルを復元でき、過去の仮説を現行版の事実へ繰り上げないこと。
3. WRLinuxのビルド済みイメージ1つと実行ファイル1つで、ファイル・パッケージ・レシピ・パッチ後コードを担当者が別環境から追えること。異なる成果物や異なるパッチ後コードを渡すと照合不一致になること。
4. HTMLの経路図・本文から次の観測を選べること。実機ログを渡していないケースで原因確定と書かないこと。
