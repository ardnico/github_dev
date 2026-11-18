"""Export a finished run without redundant drafts or byte-identical evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile


PREFERRED = ("report.txt", "report.html", "visuals.json", "presentation.json",
             "input.json", "record.json", "usage.json", "start.json",
             "codegraph.txt", "codegraph-preparation.json")


def category(relative):
    if relative in ("report.txt", "report.html", "visuals.json", "presentation.json") or relative.startswith(("reference/", "perspectives/")):
        return "reader"
    if relative in ("input.json", "record.json", "usage.json", "start.json"):
        return "execution"
    return "evidence"


def export(run, output):
    run = Path(run).resolve()
    output = Path(output).absolute()
    if output.exists() or output.is_relative_to(run):
        raise ValueError("output must be a new file outside the run")
    record = json.loads((run / "record.json").read_text(encoding="utf-8"))
    if record.get("status") not in ("completed", "blocked", "failed"):
        raise ValueError("run has not finished")
    files = [p for p in run.rglob("*") if p.is_file()]
    files.sort(key=lambda p: (PREFERRED.index(p.relative_to(run).as_posix()) if p.relative_to(run).as_posix() in PREFERRED else len(PREFERRED), p.relative_to(run).as_posix()))
    seen = {}
    included = []
    aliases = {}
    dropped = []
    for path in files:
        relative = path.relative_to(run).as_posix()
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != run and parent.is_relative_to(run)):
            raise ValueError("symlink in run cannot be exported: " + relative)
        if relative == "draft.txt":
            dropped.append(relative)
            continue
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if sha in seen:
            aliases[relative] = seen[sha]
        else:
            archive_path = category(relative) + "/" + relative
            seen[sha] = archive_path
            included.append((path, archive_path))
    manifest = {"schema_version": 1, "run_id": record["run_id"],
                "reader": "reader/report.html" if any(name == "reader/report.html" for _, name in included) else "reader/report.txt",
                "included": [name for _, name in included],
                "source_paths": {name: p.relative_to(run).as_posix() for p, name in included},
                "aliases": aliases, "omitted_work_files": dropped,
                "note": "reader=閲覧資料、evidence=索引と照会の原資料、execution=入力・統計。原レポート中のファイル名はsource_paths/aliasesで読み替える。"}
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path, archive_path in included:
                    archive.write(path, archive_path)
                archive.writestr("bundle-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        print(export(args.run, args.output))
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
