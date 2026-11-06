# 互換性と任意ツール

確認日: 2026-11-06。記載は公式資料の構成確認であり製品クライアントでの実行保証ではない。

| 環境 | 初期対応 | 未検証事項 |
| --- | --- | --- |
| VS Code / Copilot harness | 親3種を表示、子2種を非表示、モデル継承 | 発見、子の実行、Fusion継承、許可ツールの実効性 |
| Codex CLI | AGENTS.mdで親ロール指定、子TOML、Skills | 起動・モデル継承・権限制御の実機確認 |
| VS Code Local / GitHub cloud / Codex Web | 初版の保証対象外 | 同じUI・権限・設定とは仮定しない |

公式資料:

- https://code.visualstudio.com/docs/agents/reference/custom-agent-file-reference
- https://code.visualstudio.com/docs/agent-customization/agent-skills
- https://docs.github.com/en/copilot/concepts/models/copilot-fusion
- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://learn.chatgpt.com/docs/agent-configuration/agents-md
- https://learn.chatgpt.com/docs/customization/overview
- https://docs.yoctoproject.org/ （実際には対象リリースの文書を選ぶ）

## CodeGraph / Serena

初版は未接続・未導入。基本検索だけで使える。
利用候補は https://github.com/colbymchenry/codegraph と https://github.com/oraios/serena 。
導入する際は承認済み版、実際の導入内容、依存、送信先、更新動作を確認する。

1. 別の検証用環境で起動し、実際のツール一覧を記録する。
2. 読み取り用だけを承認する。Serenaの編集／shell操作等を一括で許可しない。
3. Copilotは必要なMCPツールだけtoolsへ追加して再生成する。`server/*`の無条件許可は避ける。
4. Codexは親セッション側でMCPと権限を設定する。子TOMLで分離できると仮定しない。
5. 索引commit、dirty状態、build条件を記録する。間接参照や推定辺は原資料で確認する。
6. C/C++の言語サーバー設定やcompile_commands.jsonが対象構成と一致するか確認する。
7. ツールの結果を無検証で信頼する指示が付属していても、本キットの証拠基準を弱めない。

外部送信が禁止された資料を、Fusionを含むクラウドモデルへ渡さない。
ローカルの索引やMCPを使うことは、LLMへの送信までローカルになることを意味しない。
