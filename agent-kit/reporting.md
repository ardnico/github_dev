# sourceレポート表示契約

UTF-8のreport.txtを「初見で全体像が分かり、根拠まで追える」順に作る。仕様書との一致はcompareまで判定しない。静的解析結果を承認済み仕様と呼ばない。

## 共通の先頭

1. 要約（何をする実装か、公開入口、主要なデータ・制御経路を数行）。
2. 対象・版・構成（commit、dirty差分、対象ファイル、関連ヘッダ、CodeGraph DB/索引、ビルド条件、外部依存）。未確認は明示する。
3. 読み方（入口から終了までの短い経路、今回の深掘り対象、未探索範囲）。

## driverの本体

4. 登録と公開インタフェース台帳：PCI/platform等のID表とdriver登録、netdev/file_operations/ethtool/sysfs/ioctl等、実際に登録された入口とユーザー側の到達手段。未登録の慣用APIを創作しない。open/close/read/write/ioctlがない場合は「該当なし」と根拠を書く。
5. 関連構造体・ヘッダ台帳：中心となるper-device構造体、queue/ring/descriptor、状態enum、ops表、同期primitive。定義元ヘッダと所有者・生成時点・参照経路・解放時点を示す。必要なメンバだけ選び、全文転記しない。外部ヘッダは利用APIと未解析境界を分ける。
6. シナリオ別説明：probe成功/各失敗巻き戻し、open/close、ioctl等の公開操作、TX/RX・read/write、remove/shutdown/PMを、入口→前提→処理順→状態変化→戻り値/利用者への結果→異常系→後始末で書く。重要な遷移に証拠IDを付ける。
7. 非同期・IRQ地図：request_irqのvector/登録点、デバイス割り込み許可、hard IRQ handler、threaded IRQ（存在するときだけ）、NAPI/workqueue/tasklet/timer/kthread、再投入元、共有状態とlock、mask/unmask、同期と解放順を区別する。`request_threaded_irq`等の登録がない限り「IRQスレッド」を創作しない。IRQからNAPIへ移る場合はその経路を明示。
8. 資源・排他台帳：PCI/BAR/MMIO、DMA map/coherent、IRQ、netdev、NAPI、worker等を取得者・所有者・利用者・停止条件・解放者で追い、成功/失敗/removeの各経路に紐づける。
9. 要確認台帳：優先度、観測事実、未証明の疑問、あり得る影響、必要な原資料・試験を1項目ずつ書く。不具合と断定しない。
10. 証拠索引：E-01形式で対象相対パス:関数:行範囲、CodeGraphの照会と原ソース照合、coverage/parse_error、観測・推論の別を示す。「付近」で済ませず、該当分岐を特定できないなら未特定と書く。

シナリオは重要度順に掘り下げる。公開API、失敗、非同期境界、停止・資源寿命を優先し、全関数を一律に詳述しない。対象外のカーネルcoreやハードウェアの契約を補完して断言しない。
