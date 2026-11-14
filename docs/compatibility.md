# 互換性と任意ツール

確認日: 2026-11-14。Codexの設定ファイル形式を公式資料と管理元の生成物で照合した。製品クライアントによる発見・実行受入は別途未実施。

| 環境 | 初期対応 | 未検証事項 |
| --- | --- | --- |
| VS Code / Copilot harness | 親3種を表示、子2種を非表示、モデル継承 | 発見、子の実行、Fusion継承、許可ツールの実効性 |
| Codex CLI | AGENTS.mdで親ロールを指示、`.agents/skills/`でDriver Skill、`.codex/agents/*.toml`で子Agentを定義 | 本キットの親ロール指示・子起動・モデル継承の実機確認 |
| VS Code Local / GitHub cloud / Codex Web | 初版の保証対象外 | 同じUI・権限・設定とは仮定しない |

公式資料:

- [Codex customization: AGENTS.md、Skills、Subagents](https://learn.chatgpt.com/docs/customization/overview)
- [Codex custom subagents: `.codex/agents/*.toml`形式と制約](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Codex local Skills: `.agents/skills/`の探索](https://learn.chatgpt.com/docs/build-skills)
- https://code.visualstudio.com/docs/agents/reference/custom-agent-file-reference
- https://code.visualstudio.com/docs/agent-customization/agent-skills
- https://docs.github.com/en/copilot/concepts/models/copilot-fusion
- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://learn.chatgpt.com/docs/agent-configuration/agents-md
- https://learn.chatgpt.com/docs/customization/overview
- https://docs.yoctoproject.org/ （実際には対象リリースの文書を選ぶ）

## Codexでの使い方

この構成はCodexで利用できる。Codexはrepoの`AGENTS.md`をプロジェクト指示として読み、`.agents/skills/`からrepo内Skillを見つける。Codex CLIでは、親Agentの役割を独立したピッカー用ファイルとしては定義せず、`AGENTS.md`の選択規則に沿って「調査・仕様照合として進めて」と依頼する。子の`evidence-researcher`と`evidence-reviewer`は`.codex/agents/*.toml`で登録する。

本キットにはこれらのファイルがあるが、Codex CLIの実行画面でSkill発見・子Agent起動・権限継承まで受け入れた記録はない。子は親のsandbox・approval・MCP権限を継承する。TOML内の「編集禁止」指示だけでは読み取り専用sandboxにならない。

## CodeGraph / Serena

本キットはCLIを導入しない。source時にDBがなく対象の`.codegraph/`が未作成または空なら、解析Agentが一度だけ`codegraph init <root> --local-only`でローカルSQLite DBを作成する。source完了には索引と照会が必須。MCP接続は任意の照会経路であり、CLIでもよい。仕様解析は単独実行できる。
本キットの対象は https://github.com/colbymchenry/codegraph 。同名の別CLI https://github.com/lzehrung/codegraph とはDB/manifestの判定とオプションが異なる。Serenaは補助候補: https://github.com/oraios/serena 。
導入する際は承認済み版、実際の導入内容、依存、送信先、更新動作を確認する。

1. CLIは事前に承認済み版を検証環境へ導入する。DB不在時のAgent初期化前に対象・保存先・テレメトリ設定を確認する。CodeGraphは匿名使用統計の設定を持つため、社内方針に応じて無効化する。
2. 読み取り用だけを承認する。Serenaの編集／shell操作等を一括で許可しない。
3. `codegraph`という名前だけで実装を判定しない。`@colbymchenry/codegraph`の`status <root> --json`は`projectPath`/`indexPath`形式。`@lzehrung/codegraph` 3.1.3の`schemaVersion`/`manifestPath`形式は別製品で、`--strict`を受け付けず、DBがあっても`initialized: false`になり得る。対象実装を確定してから`--strict`でDB状態を確認し、CLI照会する。MCPを使うなら、ホストの実際のツール名とDB参照先を確認して必要なツールだけ許可する。`server/*`の無条件許可は避ける。
4. Codexは親セッション側でMCPと権限を設定する。子TOMLで分離できると仮定しない。
5. DBの実体、対象root、解析commit、dirty状態、build条件、statusと照会結果を記録する。DB自体がGit commitや構成の一致を保証するとは仮定せず、差分と原資料で確認する。
6. C/C++の言語サーバー設定やcompile_commands.jsonが対象構成と一致するか確認する。
7. ツールの結果を無検証で信頼する指示が付属していても、本キットの証拠基準を弱めない。

外部送信が禁止された資料を、Fusionを含むクラウドモデルへ渡さない。
ローカルの索引やMCPを使うことは、LLMへの送信までローカルになることを意味しない。
