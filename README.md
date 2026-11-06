# github_dev — Agent Kit v0.1

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
4. 例: `analysis-manager`を選び「このドライバの終了処理を仕様と照合。変更は不要」と依頼する。
5. 子の実行時モデル、ツール、返却結果をUIで確認する。子へのFusion継承は未検証。

Copilot向け定義は`.github/agents/`、Skillsは`.github/skills/`。
`agents`や`handoffs`等のLocal専用設定は生成しない。Fusionはモデル実行の仕組みであり、子の起動機構ではない。
調査用のCopilot定義はread/search/web/agentを中心にし、shell/editを公開しない。
OS調査コマンドはユーザーが収集した出力を渡すか、別途許可した実行環境で取得する。

## Codex CLIで使う

1. 対象プロジェクトのルートでCodexを起動する。初回調査は親セッションをread-only相当の権限に設定する。
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

## 保守と検証

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
