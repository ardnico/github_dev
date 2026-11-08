# sourceレポート表示契約

UTF-8のreport.txtを「初見で全体像が分かり、根拠まで追える」順に作る。仕様書との一致はcompareまで判定しない。静的解析結果を承認済み仕様と呼ばない。読者用の報告、詳細参照、索引照会の生ログ、実行統計を混ぜない。

## 共通の先頭

1. 要約（何をする実装か、公開入口、主要なデータ・制御経路を数行）。
2. 対象・版・構成（commit、dirty差分、対象ファイル、関連ヘッダ、CodeGraph DB/索引、ビルド条件、外部依存）。未確認は明示する。
3. 読み方（入口から終了までの短い経路、今回の深掘り対象、未探索範囲）。対象の比較候補と、根拠のない「独自」主張を区別する。

## driverの本体

4. **特徴カードと条件別分岐**：対象が何を公開し、どのデバイスID/revision/CONFIGでチャネル数・IRQ方式・PHY/PTP/PMなどが変わるかを、条件→動作→影響→原ソース根拠で先に示す。一般的な機構と比較済みの差分を分ける。「独自」と呼ぶには比較対象のドライバ名・commit・同条件・差分の根拠を併記する。比較がなければ「特徴候補／未比較」。実装上の懸念は特徴と分離する。
5. 登録と公開インタフェース台帳：PCI/platform等のID表とdriver登録、netdev/file_operations/ethtool/sysfs/ioctl等、実際に登録された入口とユーザー側の到達手段。未登録の慣用APIを創作しない。open/close/read/write/ioctlがない場合は「該当なし」と根拠を書く。
6. 関連構造体・ヘッダ台帳：中心となるper-device構造体、queue/ring/descriptor、状態enum、ops表、同期primitive。定義元ヘッダと所有者・生成時点・参照経路・解放時点を示す。必要なメンバだけ選び、全文転記しない。外部ヘッダは利用APIと未解析境界を分ける。
7. シナリオ別説明：probe成功/各失敗巻き戻し、open/close、ioctl等の公開操作、TX/RX・read/write、remove/shutdown/PMを、入口→前提→処理順→状態変化→戻り値/利用者への結果→異常系→後始末で書く。重要な遷移に証拠IDを付ける。
8. 非同期・IRQ地図：request_irqのvector/登録点、デバイス割り込み許可、hard IRQ handler、threaded IRQ（存在するときだけ）、NAPI/workqueue/tasklet/timer/kthread、再投入元、共有状態とlock、mask/unmask、同期と解放順を区別する。`request_threaded_irq`等の登録がない限り「IRQスレッド」を創作しない。IRQからNAPIへ移る場合はその経路を明示。
9. 資源・排他台帳：PCI/BAR/MMIO、DMA map/coherent、IRQ、netdev、NAPI、worker等を取得者・所有者・利用者・停止条件・解放者で追い、成功/失敗/removeの各経路に紐づける。
10. 要確認台帳：優先度、観測事実、未証明の疑問、あり得る影響、必要な原資料・試験を1項目ずつ書く。不具合と断定しない。
11. 証拠索引：E-01形式で対象相対パス:関数:行範囲、CodeGraphの照会と原ソース照合、coverage/parse_error、観測・推論の別を示す。「付近」で済ませず、該当分岐を特定できないなら未特定と書く。

## 図と別HTMLの契約

- sourceの各完了runには、読者向けの`report.txt`、シーケンスと分岐を記述する`visuals.json`、単体で閲覧できる`report.html`、元レポートとHTMLのハッシュを結ぶ`presentation.json`を持たせる。HTMLは追加の説明資料であり、原レポートや証拠を置き換えない。
- 最低限「probe→公開」「open→TX→IRQ/NAPI」「RX IRQ→NAPI→受け渡し」「close/remove」を独立した図にする。実装上存在しないイベントは描かない。異常経路は根拠が確認できた場合に追加する。図は5主体以内に分割し、矢印には短い動作名、別掲で`path:line`の根拠、hard IRQ/NAPI/worker等の文脈を示す。
- `visuals.json`は`tools/render_source_report.py`の検証契約に従う。特徴行の`comparison`は`uncompared/common/different/unknown`のいずれか。`different`には比較元`baseline`を必須とする。ただしツールは証拠の意味までは検証できないため、親とレビュー担当が比較元・条件・行を独立確認する。
- HTMLはネットワーク接続・外部CDN不要。図はSVGと表で表示し、本文は引用元`report.txt`を改変せず参照用に収録。生成は`finish`後に実行し、`presentation.json`のハッシュで既存の完了runに紐づける。生成に失敗したらsource解析自体を遡って成功と偽らず、表示資料未完成と報告する。

## 成果物・証拠・作業物

- `report.txt`は読む人向けの結論、特徴カード、版・条件、代表経路、未確認事項。解析コマンド全文、ツールの初期化経緯、モデル統計は混ぜず、`codegraph.txt`、`codegraph-preparation.json`、`record.json`に場所を示す。
- 追加の詳細参照が必要なら`reference/`に条件表・インタフェース表・資源表を置く。図と異なる事実を二重に手入力せず、同じ根拠IDを参照する。
- `draft.txt`、`codegraph-evidence.txt`等の入力作業物はrun外で作り、`finish`で正本の`report.txt`と`codegraph.txt`へ固定する。個別照会を`query-01`等で別途保存する場合、同じ全文を集約ログへ複製しない。配布ZIPは`tools/export_run.py`で`reader/`（閲覧資料）、`evidence/`（索引・照会）、`execution/`（入力・統計）に分類し、同一バイト列を除く。`bundle-manifest.json`に元の名前と別名を記録する。run自体の構造は変えない。

シナリオは重要度順に掘り下げる。公開API、失敗、非同期境界、停止・資源寿命を優先し、全関数を一律に詳述しない。対象外のカーネルcoreやハードウェアの契約を補完して断言しない。
