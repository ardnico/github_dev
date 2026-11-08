"""Prepare a source run using a pinned, isolated CodeGraph 1.6.2 index."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from urllib.parse import quote


INDEX_DIR = ".codegraph-colbymchenry"
VERSION = "1.6.2"


def stamp():
    return datetime.now(timezone.utc).isoformat()


def verify_index(db, source, files):
    """Check selected files against the graph, not just the status summary."""
    checked = []
    uri = "file:" + quote(str(db)) + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise ValueError("CodeGraph SQLite integrity check failed")
        for table in ("files", "nodes", "edges"):
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                raise ValueError("CodeGraph DB missing table: " + table)
        for relative in files:
            path = source / relative
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(source):
                raise ValueError("Invalid or missing scope file: " + relative)
            row = connection.execute("SELECT content_hash, errors FROM files WHERE path=?", (relative,)).fetchone()
            if row is None:
                raise ValueError("Scope file absent from CodeGraph index: " + relative)
            data = path.read_bytes()
            data.decode("utf-8")
            actual = hashlib.sha256(data).hexdigest()
            if row[0] != actual:
                raise ValueError("Scope file differs from CodeGraph index: " + relative)
            if row[1] not in (None, "", "[]"):
                raise ValueError("CodeGraph parse errors for scope file: " + relative)
            checked.append({"path": relative, "sha256": actual})
    return checked


def verify_status(status, source, index_dir):
    if not isinstance(status, dict):
        raise ValueError("CodeGraph status is not a JSON object")
    if status.get("initialized") is not True:
        raise ValueError("CodeGraph index is not initialized")
    if not isinstance(status.get("projectPath"), str) or Path(status["projectPath"]).resolve() != source:
        raise ValueError("CodeGraph status resolved another project root")
    if not isinstance(status.get("indexPath"), str) or Path(status["indexPath"]).resolve() != index_dir:
        raise ValueError("CodeGraph status resolved another index directory")
    if status.get("version") != VERSION:
        raise ValueError("CodeGraph status version differs from pinned executable")
    index = status.get("index")
    if not isinstance(index, dict) or index.get("state") != "complete":
        raise ValueError("CodeGraph index is not complete")
    if index.get("reindexRecommended") is not False or type(index.get("pendingRefs")) is not int or index["pendingRefs"] != 0:
        raise ValueError("CodeGraph index requires reindexing or reference resolution")
    if index.get("builtWithVersion") != VERSION or type(index.get("currentExtractionVersion")) is not int or type(index.get("builtWithExtractionVersion")) is not int or index["builtWithExtractionVersion"] != index["currentExtractionVersion"]:
        raise ValueError("CodeGraph index was built with a different extraction version")
    if status.get("worktreeMismatch", "missing") is not None:
        raise ValueError("CodeGraph index belongs to a different worktree")
    changes = status.get("pendingChanges")
    if not isinstance(changes, dict) or any(type(changes.get(k)) is not int or changes[k] != 0 for k in ("added", "modified", "removed")):
        raise ValueError("CodeGraph index has pending changes")
    if type(status.get("fileCount")) is not int or status["fileCount"] <= 0:
        raise ValueError("CodeGraph index contains no files")


def prepare(run, executable=None, invoke=None):
    run = Path(run).resolve()
    start = json.loads((run / "start.json").read_text(encoding="utf-8"))
    inputs = json.loads((run / "input.json").read_text(encoding="utf-8"))
    if start["stage"] != "source" or start["status"] != "running" or (run / "record.json").exists():
        raise ValueError("Only an unfinished source run can prepare CodeGraph")
    if (run / "codegraph-preparation.json").exists():
        raise ValueError("Preparation already attempted; inspect its log before a new run")
    if hashlib.sha256((run / "input.json").read_bytes()).hexdigest() != start["input_sha256"]:
        raise ValueError("Source input snapshot was modified")
    source_input = Path(inputs["source_root"])
    source = source_input.resolve()
    project = Path(start["project"]).resolve()
    if not source_input.is_absolute() or not source.is_dir() or not source.is_relative_to(project):
        raise ValueError("source_root must be an absolute directory inside the recorded project")
    index_dir = source / INDEX_DIR
    db = index_dir / "codegraph.db"
    invoke = invoke or subprocess.run
    env = dict(os.environ, CODEGRAPH_TELEMETRY="0", CODEGRAPH_DIR=INDEX_DIR)
    output = {"source_root": str(source), "index_path": str(index_dir), "db": str(db),
              "started_at": stamp(), "commands": [], "required_cli_version": VERSION}

    def call(*args):
        result = invoke([command, *args], cwd=source, env=env, text=True,
                        capture_output=True, timeout=1800, check=False)
        output["commands"].append({"args": list(args), "exit_code": result.returncode,
                                   "stdout": result.stdout, "stderr": result.stderr, "at": stamp()})
        if result.returncode:
            raise ValueError("CodeGraph command failed: " + " ".join(args))
        return result

    try:
        if not executable or not Path(executable).is_absolute() or not Path(executable).is_file() or not os.access(executable, os.X_OK):
            raise ValueError("Specify an installed executable using --codegraph-bin <absolute path>; no automatic installation")
        command = str(Path(executable).resolve())
        output["cli_bin"] = command
        output["codegraph_dir_env"] = INDEX_DIR
        output["telemetry_env"] = "0"
        if index_dir.is_symlink() or db.is_symlink():
            raise ValueError("Symlinked CodeGraph index is not supported")
        files = inputs.get("scope", {}).get("resolved_files") if isinstance(inputs.get("scope"), dict) else None
        if inputs.get("domain") in ("driver", "mw") and (not isinstance(files, list) or not files):
            raise ValueError("driver/mw source needs scope.resolved_files")
        if files is not None and (not isinstance(files, list) or not all(isinstance(f, str) and f and not Path(f).is_absolute() and ".." not in Path(f).parts for f in files) or len(files) != len(set(files))):
            raise ValueError("Invalid scope.resolved_files")
        version = call("version").stdout.strip()
        output["detected_cli_version"] = version
        if version != VERSION:
            raise ValueError("Unsupported CodeGraph CLI version: " + version + "; expected " + VERSION)
        probe = call("status", str(source), "--json")
        try:
            identity = json.loads(probe.stdout)
        except json.JSONDecodeError as error:
            raise ValueError("Unrecognized CodeGraph status JSON") from error
        if not isinstance(identity, dict):
            raise ValueError("Unrecognized CodeGraph status object")
        if "manifestPath" in identity or "schemaVersion" in identity:
            raise ValueError("Wrong codegraph CLI (@lzehrung/codegraph format); existing data was not modified")
        if not all(key in identity for key in ("initialized", "projectPath", "indexPath")):
            raise ValueError("Unrecognized CodeGraph provider")
        if not isinstance(identity["projectPath"], str) or not isinstance(identity["indexPath"], str) or Path(identity["projectPath"]).resolve() != source or Path(identity["indexPath"]).resolve() != index_dir:
            raise ValueError("CodeGraph status resolved another project or index directory")
        if not db.is_file():
            if index_dir.exists() and (not index_dir.is_dir() or any(index_dir.iterdir())):
                raise ValueError("Nonempty isolated index without DB; inspect manually")
            if identity["initialized"] is not False:
                raise ValueError("CLI reports an index but the expected DB is absent")
            output["action"] = "init"
            call("init", str(source), "--yes")
        else:
            output["action"] = "reuse"
            if identity["initialized"] is not True:
                raise ValueError("Isolated CodeGraph DB exists but selected CLI does not recognize it")
        if not db.is_file():
            raise ValueError("Isolated CodeGraph DB absent after init")
        checked = json.loads(call("status", str(source), "--json").stdout)
        verify_status(checked, source, index_dir)
        output["verified_files"] = verify_index(db, source, files or [])
        output["status"] = "prepared"
        return output
    except (ValueError, UnicodeError, sqlite3.DatabaseError, subprocess.TimeoutExpired, OSError) as error:
        output.update(status="blocked", error=str(error))
        return output
    finally:
        output["ended_at"] = stamp()
        path = run / "codegraph-preparation.json"
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
            json.dump(output, stream, ensure_ascii=False, indent=2)
            stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--codegraph-bin", help="Preinstalled @colbymchenry/codegraph 1.6.2 executable, absolute path")
    args = parser.parse_args()
    try:
        output = prepare(args.run, executable=args.codegraph_bin)
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))
    print(output["status"] + ": " + output["source_root"])
    if output["status"] != "prepared":
        print(output["error"], file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
