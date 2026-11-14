# sourceレポート表示契約

完了したdriver source runは、入口から停止・解放までの仕組みを図と証拠から理解できる一組の文書を作る。`report.txt`は短い案内ページ、深い解析はrun内の`perspectives/`に置く7つのMarkdown文書とする。レポートは実装の静的解析であり、仕様との一致や実機上の挙動を確定しない。

## report.txt: 案内ページ

冒頭に次を短く書く。

1. 何をするdriverか、実際に確認できた入口、主な制御／データ経路。
2. 対象root、commit、dirty差分SHA-256、対象ファイル、kernel/vendor/board/build版、CodeGraph索引版とroot。取得不能は理由とともに「不明」とする。
3. 観測・推論・不明の凡例、今回の範囲、未探索範囲。
4. `perspectives/00-overview.md`から`perspectives/06-open-questions-and-evidence.md`までのリンクまたは相対パス一覧と各文書の役割。

## 観点別文書

以下のファイル名で7件すべてを作る。ある機能が見つからない場合は文書を省かず、「該当機能を確認できず」と探索範囲・照会・原ソース根拠を記す。探索不足なら「未探索」とし、非存在と混同しない。各文書に対象版と対象範囲を記し、同じ説明を繰り返さず相互参照する。

### `00-overview.md` — 全体像

- 初見向けの要約、主要コンポーネント、外部との境界、開始から停止までの読み順。
- Mermaid `flowchart` でバス／デバイス登録、probe、中心状態、公開サブシステム、TX/RX等の主要経路、IRQ/deferred work、removeをつなぐ。
- ノードと矢印にE-IDを付ける。推定ノードは「推論」、外部仕様で未確認の端点は「契約不明」と明記する。

### `01-registration-interfaces.md` — 登録と公開インタフェース

- PCI/platform/USB等のID表と、実際に使われるdriver登録構造体・callbackの対応表。
- netdev、file_operations、ethtool、sysfs、ioctl、debugfs等の実登録された公開入口、登録先、利用者からの到達経路。
- open/close/read/write/ioctlなどを想定だけで足さない。未確認項目は、検索・CodeGraph照会と登録元の証拠を示して「該当なし」または「未探索」と区別する。
- 各公開入口から処理完了または返却までの最短経路図を置く。

### `02-data-and-state.md` — データ構造と状態

- 中心となるper-device構造体、queue/ring/descriptor、重要なenum、ops table、lock/atomic/completion等を選び、定義ヘッダとメンバの意味を追う。
- 各データの作成時、所有者、参照者、状態変更者、解放時を表にする。構造体全文は転記しない。
- 実装された状態遷移をMermaid `stateDiagram-v2`で示す。遷移を発生させる関数とE-IDを各矢印に示す。遷移が証明できない場合は線を引かず、未確定箇所を説明する。
- 外部ヘッダやカーネルcoreは利用境界と未解析契約を明記する。

### `03-scenarios.md` — シナリオ別処理

- probe成功、各失敗巻き戻し、実登録された公開操作、TX/RXやread/write、PM/shutdownがある場合はその各経路を分ける。
- 各シナリオを「入口 → 前提 → 実行順 → 状態・共有データ変化 → 戻り値／利用者への結果 → 異常系 → 後始末」の順に説明する。
- 重要な通常系と失敗系をMermaid `sequenceDiagram`で示す。参加者はソースで確認できた主体だけにし、呼び出し矢印・戻り・非同期投入にE-IDを付ける。
- 成功だけでなく、部分初期化後に何が巻き戻されるか、エラー伝播、再試行・重複操作の条件を調べる。証拠がない挙動を補わない。

### `04-irq-and-async.md` — IRQと非同期処理

- IRQの要求点・vector・handler、デバイス側mask/unmask・割り込み許可、hard IRQ、threaded IRQ、NAPI、workqueue/tasklet/timer/kthreadを別々に列挙する。実在しないcontextは作らない。
- 割込み／イベント源からhard IRQ、deferred context、完了・再投入までをflowchartまたはsequence diagramで示す。登録、投入、実行、完了、再投入、停止の各辺にE-IDを付ける。
- contextごとにsleep可否の根拠、使うlock、共有状態、lockの取得順、再投入元、mask解除条件を示す。カーネルAPI名だけから実行contextを過剰に推定しない。
- cancel/freeの前に新規投入源・実行中処理を止める主体と同期方法を記録する。静的証拠だけで競合成立を断定しない。

### `05-resources-and-lifecycle.md` — 資源とライフサイクル

- PCI/BAR/MMIO、DMA map/coherent、IRQ、netdev、NAPI、worker、timer、memory、userspace mapping等を、取得者／所有者／利用者／停止条件／解放者の台帳にする。
- probe成功、各失敗ラベル、remove/shutdown/PMごとの取得・解放・巻戻しを対応付ける。devm管理と非同期処理の停止は別の論点として扱う。
- remove/shutdownの処理順をsequence diagramまたは依存flowchartにし、「再投入停止 → IRQ/DMA/workerの排出・同期 → 利用中資源解放」がソース上でどうつながるかE-IDで示す。API呼び出し順の一部だけで安全性を結論しない。
- MMIO、PCI config、DMA buffer、RAM、userspace mappingを区別し、各資源の寿命がデバイスや非同期処理の寿命より短くならないことを確認する。

### `06-open-questions-and-evidence.md` — 要確認事項と証拠

- 要確認事項は優先度、観測事実、未証明の問い、成立条件に応じた影響、次に必要なソース／仕様／設定／実機試験で記す。未確認の疑いを不具合と断定しない。
- 探索範囲、対象外ディレクトリ、条件付きコンパイル、parse error、未解決関数ポインタ、未解析外部境界を列挙する。
- E-01形式の証拠索引を置く。各項目に相対パス、関数／登録構造体名、行範囲、支える主張、CodeGraph照会の有無、観測／推論の別を含める。短い引用は必要最小限にする。
- CodeGraphの辺は候補として扱い、重要な矢印・資源解放・失敗分岐を原ソースで照合する。結果が見つからない検索は「実装なし」の証明にしない。

## 図と証拠の規則

- 図はMermaidの`flowchart`、`sequenceDiagram`、`stateDiagram-v2`で記述し、複雑な経路を文章だけで済ませない。
- 実装上観測できるノード・矢印・状態遷移だけを描く。図のすべての重要な矢印に、本文のE-IDを付ける。根拠が一部しかない場合、実線で確定経路にせず、推論または不明な辺として明確にする。
- IRQ thread、NAPI、workqueue、API、戻り値、資源寿命を慣例から補完しない。登録や生成元が原ソースで確認できなければ「未確認」とする。
- 製品図としてMermaidが描画されない表示環境でも追えるよう、図の直前／直後に通常文で参加者と経路の要約を書く。

## 深さと判断

全関数を一律に説明せず、実登録入口、状態・排他、失敗巻き戻し、非同期境界、停止と資源寿命を優先して深める。実装由来の動作は「観測」、コードからの読み取りは「推論」、追加証拠が必要な点は「不明」と記す。仕様資料が入力に含まれてもsourceでは開かず、実装との一致は独立したcompare runまで判定しない。
