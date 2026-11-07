"""Prepare a source run's local CodeGraph index, without installing or reindexing tools."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys


def stamp():
    return datetime.now(timezone.utc).isoformat()


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
    source = Path(inputs["source_root"]).resolve()
    project = Path(start["project"]).resolve()
    if not source.is_dir() or not source.is_relative_to(project):
        raise ValueError("source_root must be inside the recorded project")
    db_dir = source / ".codegraph"
    db = db_dir / "codegraph.db"
    if db_dir.is_symlink() or db.is_symlink():
        raise ValueError("Symlinked CodeGraph index is not supported")
    command = executable or shutil.which("codegraph")
    invoke = invoke or subprocess.run
    env = dict(os.environ, CODEGRAPH_TELEMETRY="0")
    output = {"source_root": str(source), "db": str(db), "started_at": stamp(), "commands": []}

    def call(*args):
        result = invoke([command, *args], cwd=source, env=env, text=True, capture_output=True, timeout=1800, check=False)
        output["commands"].append({"args": list(args), "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "at": stamp()})
        if result.returncode:
            raise ValueError("CodeGraph command failed: " + " ".join(args))
        return result

    try:
        if not command:
            raise ValueError("CodeGraph CLI not installed; do not auto-install")
        call("version")
        if not db.is_file():
            if db_dir.exists() and (not db_dir.is_dir() or any(db_dir.iterdir())):
                raise ValueError("Nonempty .codegraph without DB; inspect manually")
            output["action"] = "init"
            call("init", str(source), "--local-only")
        else:
            output["action"] = "reuse"
        if not db.is_file():
            raise ValueError("CodeGraph DB absent after init")
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as connection:
            connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        call("status", str(source), "--json", "--strict")
        output["status"] = "prepared"
        return output
    except (ValueError, sqlite3.DatabaseError, subprocess.TimeoutExpired, OSError) as error:
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
    args = parser.parse_args()
    try:
        output = prepare(args.run)
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))
    print(output["status"] + ": " + output["source_root"])
    if output["status"] != "prepared":
        print(output["error"], file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
