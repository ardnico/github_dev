---
name: analyze-driver-evidence
description: Linuxドライバの理解・レビュー・仕様照合で、コールバック、初期化と終了、I/O、IRQ、資源寿命を証拠から追う。C/Rustドライバの調査時に使う。
---

# ドライバの証拠解析

1. 対象ソース、kernel/vendor版、Kconfig、ハードウェア仕様、解析シナリオを記録する。
2. 登録構造体・ID・操作テーブルから入口を特定する。関数名だけでprobe/open等を認定しない。
3. 初期化成功、途中失敗、remove/shutdownを組にして読む。資源ごとに取得、所有者、利用者、解放を記録する。
4. 公開I/Oから完了まで追い、IRQ、work、timer、kthreadなどの非同期境界で投入元・実行先・共有状態を記録する。
5. process / hard IRQ / threaded IRQ / deferred contextを分け、sleep可否、ロック、参照寿命を確認する。
6. MMIO、PCI config、DMA、RAM、userspace mappingを区別する。レジスタ仕様不明時は推測で埋めない。
7. 終了順序を定型化しない。新規要求・IRQ・DMA・workの生成源と実行中処理が停止してから対応資源が解放されるかを確認する。
8. IRQ登録をデバイス割り込み有効化と混同しない。cancelだけで再投入を防げると考えない。
9. 関数ポインタや条件付きコンパイルの未解決部分を明示する。devm管理でも非同期停止は別問題として確認する。
10. `agent-kit/reporting.md`の表示契約に従う。関連構造体・定義ヘッダと外部ヘッダ、実登録された公開操作（open/close/ioctl等の有無）、IRQ hard/threaded/NAPI/work等の移行、成功・失敗・停止の資源寿命を台帳とシナリオで示す。
11. 冒頭に要約と対象版・未確認のビルド条件、末尾に優先度つき要確認事項とE-01形式の証拠索引を置く。重要箇所だけ詳細化し、実装由来の仕様候補と実際の仕様を区別する。

CodeGraphの経路は候補。Serenaの参照も対象ビルド設定に依存する。対象版のソースを優先する。
実機のunbind、モジュール操作、広範囲トレース、MMIO操作は別の明示許可なしに実行しない。
