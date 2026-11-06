---
name: analyze-yocto-evidence
description: Yocto、BitBake、Wind River Linuxのレシピ・レイヤー・OS構成を解析する。設定の由来、依存、パッチ、イメージ反映、native/target/SDK差分の調査に使う。
---

# OS・レシピの証拠解析

1. Yocto/BitBake/vendor版、MACHINE、DISTRO、image、レイヤーrevisionを記録する。
2. .bb / .bbappend / .inc / .bbclass / confを追い、override、provider、version、BBMASK、レイヤー優先度を確認する。
3. SRC_URI/SRCREV、パッチ、PACKAGECONFIG、DEPENDS/RDEPENDS、install/package、image収録を別々に確認する。
4. native、target、nativesdk、SDK host/targetを混同しない。同じ変数名でも評価文脈を記録する。
5. 提供済みのbitbake -e、bitbake-layers show-layers/show-appends、タスクログ、manifestを使って展開後を確認する。
6. コマンド実行は対象環境・許可を確認してから行う。メタデータ解析もPythonを評価し得るため、未知のレイヤーを単なる安全なテキストと扱わない。
7. 設定記述→有効値→生成物→実機動作の4段階を分離する。環境がなければ静的候補までとする。
8. kernel config/patch、module収録とロード、systemd/udev、ユーザー権限、MW起動の接点を確認する。
9. 結論には変数の由来、適用条件、対象構成、証拠、不明点を付ける。

レシピが存在してもimage収録の証明ではない。ビルド成功も実機動作の証明ではない。
clean/cleansstate、fetch、ビルド、devtool変更、デプロイは調査の許可だけでは実行しない。
