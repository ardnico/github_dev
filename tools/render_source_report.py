"""Render a completed source run and reviewed visual data as standalone HTML."""
import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re


def escape(value):
    return html.escape(str(value), quote=True)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(data):
    if data.get("schema_version") != 1 or not isinstance(data.get("title"), str):
        raise ValueError("visuals needs schema_version=1 and title")
    for key in ("fingerprint", "variants", "sequences"):
        if not isinstance(data.get(key), list):
            raise ValueError("visuals needs " + key + " array")
    for row in data["fingerprint"]:
        if not all(isinstance(row.get(k), str) and row[k] for k in ("axis", "observed", "evidence")):
            raise ValueError("fingerprint needs axis, observed and evidence")
        if row.get("comparison") not in ("uncompared", "common", "different", "unknown"):
            raise ValueError("comparison must be uncompared/common/different/unknown")
        if row["comparison"] == "different" and not row.get("baseline"):
            raise ValueError("a difference needs an explicit baseline")
    for row in data["variants"]:
        if not all(isinstance(row.get(k), str) and row[k] for k in ("condition", "behavior", "evidence")):
            raise ValueError("variants need condition, behavior and evidence")
    ids = set()
    for sequence in data["sequences"]:
        if not re.fullmatch(r"[a-z0-9-]+", sequence.get("id", "")) or sequence["id"] in ids:
            raise ValueError("invalid or duplicate sequence id")
        ids.add(sequence["id"])
        participants = sequence.get("participants")
        messages = sequence.get("messages")
        if not isinstance(participants, list) or not 2 <= len(participants) <= 5 or not isinstance(messages, list) or not messages:
            raise ValueError("sequence needs 2-5 participants and messages")
        names = [p.get("id") for p in participants]
        if len(names) != len(set(names)) or any(not re.fullmatch(r"[a-z0-9-]+", n or "") or not p.get("label") or not p.get("context") for n, p in zip(names, participants)):
            raise ValueError("invalid sequence participant")
        for m in messages:
            if m.get("from") not in names or m.get("to") not in names or m.get("kind") not in ("call", "return", "async"):
                raise ValueError("invalid sequence message edge")
            if not all(isinstance(m.get(k), str) and m[k] for k in ("label", "evidence")):
                raise ValueError("sequence messages need label and evidence")
            if len(m["label"]) > 100:
                raise ValueError("sequence labels should be concise")
    return data


def sequence_svg(sequence):
    participants = sequence["participants"]
    messages = sequence["messages"]
    width = 210 + 205 * (len(participants) - 1)
    height = 125 + 75 * len(messages)
    x = {p["id"]: 105 + 205 * i for i, p in enumerate(participants)}
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-labelledby="title-{escape(sequence["id"])} desc-{escape(sequence["id"])}">',
             f'<title id="title-{escape(sequence["id"])}">{escape(sequence["title"])}</title>',
             f'<desc id="desc-{escape(sequence["id"])}">']
    parts.append(escape(" / ".join(f'{m["from"]} → {m["to"]}: {m["label"]}' for m in messages)))
    parts.append('</desc><defs><marker id="arrow-' + escape(sequence["id"]) + '" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z"/></marker></defs>')
    for p in participants:
        px = x[p["id"]]
        parts.append(f'<rect class="actor" x="{px-80}" y="12" width="160" height="42" rx="8"/>')
        parts.append(f'<text class="actor-label" text-anchor="middle" x="{px}" y="38">{escape(p["label"])}</text>')
        parts.append(f'<text class="context" text-anchor="middle" x="{px}" y="72">{escape(p["context"])}</text>')
        parts.append(f'<line class="lifeline" x1="{px}" x2="{px}" y1="82" y2="{height-22}"/>')
    for i, m in enumerate(messages):
        y = 117 + 75 * i
        a, b = x[m["from"]], x[m["to"]]
        direction = 1 if b >= a else -1
        start = a + direction * 12
        end = b - direction * 12
        cls = "message " + m["kind"]
        # Self-calls are represented with a short loop.
        if a == b:
            path = f'M{a} {y} h46 v20 h-46'
        else:
            path = f'M{start} {y} H{end}'
        parts.append(f'<path class="{cls}" d="{path}" marker-end="url(#arrow-{escape(sequence["id"])})"/>')
        label = escape(f'{i + 1}. {m["label"]}')
        anchor = "middle" if a != b else "start"
        tx = (a + b) // 2 if a != b else a + 12
        parts.append(f'<text class="step-label" text-anchor="{anchor}" x="{tx}" y="{y-11}">{label}</text>')
    parts.append("</svg>")
    return "".join(parts)


def table(headers, rows):
    head = "".join("<th scope=\"col\">" + escape(h) + "</th>" for h in headers)
    body = "".join("<tr>" + "".join("<td>" + escape(v) + "</td>" for v in row) + "</tr>" for row in rows)
    return '<div class="table-wrap"><table><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table></div>'


def build(run, data):
    record = json.loads((run / "record.json").read_text(encoding="utf-8"))
    inputs = json.loads((run / "input.json").read_text(encoding="utf-8"))
    report = (run / "report.txt").read_text(encoding="utf-8")
    if record.get("stage") != "source" or record.get("status") != "completed":
        raise ValueError("HTML presentation requires a completed source run")
    if digest(run / "report.txt") != record["report_sha256"] or digest(run / "input.json") != record["input_sha256"]:
        raise ValueError("run inputs or report changed after completion")
    validate(data)
    fingerprint = table(["観点", "対象で観測したこと", "比較状態", "根拠"], [
        (r["axis"], r["observed"], r["comparison"] + (f'：{r["baseline"]}' if r.get("baseline") else ""), r["evidence"])
        for r in data["fingerprint"]])
    variants = table(["成立条件", "実装上の分岐", "根拠"], [(r["condition"], r["behavior"], r["evidence"]) for r in data["variants"]])
    sequences = []
    for s in data["sequences"]:
        steps = "".join('<li><span class="kind">' + escape(m["kind"]) + "</span> " + escape(m["label"]) + " — " + escape(m["evidence"]) + "</li>" for m in s["messages"])
        sequences.append('<section id="' + escape(s["id"]) + '"><h3>' + escape(s["title"]) + '</h3><p class="muted">' + escape(s.get("note", "")) + '</p><div class="diagram">' + sequence_svg(s) + '</div><details><summary>矢印の根拠</summary><ol>' + steps + "</ol></details></section>")
    links = " ".join('<a href="#' + escape(s["id"]) + '">' + escape(s["title"]) + "</a>" for s in data["sequences"])
    css = """
    :root{color-scheme:light dark;font-family:system-ui,-apple-system,"Noto Sans JP",sans-serif;line-height:1.65;background:#f4f7f9;color:#172536}
    *{box-sizing:border-box}body{margin:0}main{max-width:1120px;margin:auto;padding:24px 24px 80px}
    header{background:#12314b;color:white;padding:24px}header>div{max-width:1072px;margin:auto}
    h1{font-size:clamp(1.5rem,3vw,2.3rem);line-height:1.3}h2{margin-top:42px;border-bottom:2px solid #d2dfe8;padding-bottom:7px}
    h3{margin-top:30px}p{max-width:83ch}a{color:#126389}header a{color:#c9edf8}
    .meta{font-size:.9rem}.notice{background:#fff1d7;border-left:5px solid #b8740b;padding:12px 17px;margin:22px 0}
    .card{background:white;border:1px solid #d7e2e9;border-radius:12px;padding:18px;margin:18px 0}
    .muted{color:#475a69}.table-wrap,.diagram{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:640px;background:white}
    th,td{text-align:left;border-bottom:1px solid #d5dfe6;padding:12px;vertical-align:top}th{background:#eaf1f6}
    .diagram{border:1px solid #d5dfe6;background:white;border-radius:10px;padding:10px;margin:12px 0}
    svg{width:100%;min-width:640px;height:auto;display:block;font:13px system-ui,sans-serif}
    .actor{fill:#e5f2fa;stroke:#3c6c86}.actor-label{font-weight:600;fill:#173b53}.context{fill:#476172;font-size:11px}
    .lifeline{stroke:#aabac3;stroke-dasharray:4 5}.message{fill:none;stroke:#235e7e;stroke-width:2}
    .message.return{stroke-dasharray:6 5}.message.async{stroke:#ac6200;stroke-dasharray:3 4}
    marker path{fill:#235e7e}.step-label{fill:#142c3b;font-size:12px}
    .kind{font-family:monospace;background:#e9f1f5;padding:2px 4px}.source{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.6 ui-monospace,SFMono-Regular,monospace}
    nav{display:flex;flex-wrap:wrap;gap:12px}details{margin:12px 0}summary{cursor:pointer;font-weight:600}
    @media(prefers-color-scheme:dark){:root{background:#12202b;color:#e8f1f6}header{background:#0b1720}a{color:#80c9ec}.muted{color:#b4c9d6}.card,.diagram,table{background:#1b303e;border-color:#3e5565}th{background:#284356}td,th{border-color:#3e5565}.notice{background:#4a3415;border-color:#e7a940}.actor{fill:#29475a;stroke:#8abbdb}.actor-label,.step-label{fill:#eff8ff}.context{fill:#bdd5e1}.lifeline{stroke:#7691a0}.message{stroke:#82c6e8}.message.async{stroke:#f1b85f}marker path{fill:#82c6e8}.kind{background:#29475a}h2{border-color:#3e5565}}
    @media print{header{background:white;color:black}main{max-width:none}details{display:block}.diagram{break-inside:avoid}}
    """
    title = escape(data["title"])
    root_note = escape(data.get("provenance", "実装の静的解析。仕様・実機による確認ではない。"))
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{css}</style></head>
<body><header><div><p class="meta">SOURCE ANALYSIS · {escape(record["run_id"])}</p><h1>{title}</h1><p>{root_note}</p></div></header>
<main><div class="notice">「独自」は同条件の別ドライバとの比較が必要。比較状態がuncomparedの行は特徴候補であり、固有性を証明しない。</div>
<nav><a href="#fingerprint">特徴カード</a><a href="#variants">条件別分岐</a>{links}<a href="#original">原レポート</a></nav>
<section id="fingerprint"><h2>特徴カード</h2>{fingerprint}</section>
<section id="variants"><h2>条件別の動作</h2>{variants}</section>
<section><h2>時系列で読む</h2><p class="muted">実線は通常の呼び出し、破線は戻りまたは非同期境界。番号に対応する根拠を図の下に表示する。</p>{''.join(sequences)}</section>
<section id="original"><h2>原レポート</h2><p>下記は元のreport.txtを改変せずに表示。照会履歴・統計・索引状態はrun内の別ファイルを参照。</p><details><summary>全文を開く</summary><div class="card source">{escape(report)}</div></details></section>
<footer class="muted">Source commit: {escape(inputs.get("source_commit", "不明"))} · HTML生成: {escape(datetime.now(timezone.utc).isoformat())}</footer>
</main></body></html>"""


def render(run, visuals):
    run = Path(run).resolve()
    data = json.loads(Path(visuals).read_text(encoding="utf-8"))
    output = run / "report.html"
    visual_target = run / "visuals.json"
    manifest = run / "presentation.json"
    if any(path.exists() for path in (output, visual_target, manifest)):
        raise ValueError("presentation already exists; use a new run")
    page = build(run, data)
    source = Path(visuals)
    if source.resolve() == visual_target.resolve():
        raise ValueError("visuals source must be outside the final run")
    for path, content in ((visual_target, source.read_text(encoding="utf-8")), (output, page)):
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
            stream.write(content)
    payload = {"schema_version": 1, "run_id": json.loads((run / "record.json").read_text(encoding="utf-8"))["run_id"],
               "source_report_sha256": digest(run / "report.txt"), "visuals_sha256": digest(visual_target), "html_sha256": digest(output)}
    with os.fdopen(os.open(manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--visuals", required=True)
    args = parser.parse_args()
    try:
        print(render(args.run, args.visuals))
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
