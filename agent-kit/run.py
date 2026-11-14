"""Record staged analysis outputs and observed usage; no LLM/tool execution."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import uuid
from urllib.parse import quote

REQUIRED = {
    "source": ("source_root", "source_commit", "dirty_state", "build_config", "domain"),
    "spec": ("spec_id", "spec_revision", "spec_files", "domain"),
    "compare": ("source_run", "spec_run", "domain"),
    "other": ("task",),
}
PERSPECTIVE_FILES = (
    "00-overview.md",
    "01-registration-interfaces.md",
    "02-data-and-state.md",
    "03-scenarios.md",
    "04-irq-and-async.md",
    "05-resources-and-lifecycle.md",
    "06-open-questions-and-evidence.md",
)


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def perspective_hashes(run, record):
    expected = record.get("perspectives_sha256", {})
    if not isinstance(expected, dict):
        raise ValueError("Invalid perspective manifest")
    if expected and set(expected) != {"perspectives/" + name for name in PERSPECTIVE_FILES}:
        raise ValueError("Invalid perspective manifest")
    for relative, sha256 in expected.items():
        path = Path(relative)
        if not path.parts or path.is_absolute() or ".." in path.parts or path.parts[0] != "perspectives":
            raise ValueError("Invalid perspective path")
        target = run / path
        if (target.is_symlink()
                or any(parent.is_symlink() for parent in target.parents if parent != run)
                or not target.is_file()
                or digest(target) != sha256):
            raise ValueError("Perspective document was modified")
    return expected


def finished_run_is_intact(run, record):
    try:
        if digest(run / "report.txt") != record.get("report_sha256"):
            return False
        if digest(run / "input.json") != record.get("input_sha256"):
            return False
        perspective_hashes(run, record)
    except (ValueError, OSError, TypeError):
        return False
    return True


def collect_perspectives(directory, run):
    source = Path(directory).expanduser().absolute()
    if source.is_symlink() or not source.is_dir() or source.resolve().is_relative_to(run):
        raise ValueError("Perspective input must be a separate, non-symlink directory")
    entries = list(source.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise ValueError("Perspective input must contain regular files only")
    if {path.name for path in entries} != set(PERSPECTIVE_FILES):
        raise ValueError("Perspective input must contain the seven required Markdown documents")
    documents = {}
    for name in PERSPECTIVE_FILES:
        data = (source / name).read_bytes()
        text = data.decode("utf-8")
        if not text.strip():
            raise ValueError("Perspective document is empty: " + name)
        documents["perspectives/" + name] = data
    return documents


def stamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Timestamp needs timezone")
    return result


def usage_check(data):
    if data.get("coverage") not in ("complete", "partial", "unavailable"):
        raise ValueError("Invalid usage coverage")
    if not isinstance(data.get("events"), list):
        raise ValueError("usage.events must be a list")
    if not data["events"] and not data.get("missing_reason"):
        raise ValueError("Empty usage needs missing_reason")
    if not data["events"] and data["coverage"] == "complete":
        raise ValueError("Empty usage cannot be complete")
    ids = set()
    nullable = ("actual_model", "input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens", "credits", "rate")
    for event in data["events"]:
        required = (*nullable, "event_id", "parent_event_id", "agent", "requested_model", "started_at", "ended_at", "evidence_source", "missing_reason")
        if any(k not in event for k in required):
            raise ValueError("Missing event field")
        if not event["event_id"] or event["event_id"] in ids:
            raise ValueError("Empty or duplicate event_id")
        ids.add(event["event_id"])
        if stamp(event["ended_at"]) < stamp(event["started_at"]):
            raise ValueError("Negative event duration")
        if any(event[k] is None for k in nullable) and not event["missing_reason"]:
            raise ValueError("Unknown metrics need missing_reason")
        if not event["evidence_source"]:
            raise ValueError("Metrics need provenance")
        for field in nullable[1:-1]:
            value = event[field]
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
                raise ValueError("Invalid numeric metric: " + field)
            if field.endswith("tokens") and value is not None and not isinstance(value, int):
                raise ValueError("Tokens must be integers")
        rate = event["rate"]
        if rate is not None:
            if not isinstance(rate, dict) or any(not rate.get(k) for k in ("currency", "unit", "effective_at", "checked_at", "source")):
                raise ValueError("Rate needs units, dates and source")
            stamp(rate["effective_at"])
            stamp(rate["checked_at"])
            for key in ("input", "output", "cached_input", "credit_multiplier"):
                value = rate.get(key)
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
                    raise ValueError("Invalid rate: " + key)
    return data


def start(project, case, stage, inputs, output_root=None):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", case):
        raise ValueError("Invalid case ID")
    project = Path(project).resolve()
    if not project.is_dir():
        raise ValueError("Project must exist")
    for key in (*REQUIRED[stage], "scope", "kit_revision", "host_version"):
        if key not in inputs or inputs[key] in (None, "", [], {}):
            raise ValueError("Missing input: " + key)
    inputs = json.loads(json.dumps(inputs))
    if stage == "spec":
        if not isinstance(inputs["spec_files"], list):
            raise ValueError("spec_files must be a list")
        inputs["spec_hashes"] = {}
        for value in inputs["spec_files"]:
            path = Path(value)
            if not path.is_absolute() or not path.is_file():
                raise ValueError("spec_files require existing absolute file paths")
            inputs["spec_hashes"][str(path)] = digest(path)
    if stage == "compare":
        inputs["dependencies"] = {}
        for dependency in ("source", "spec"):
            run = Path(inputs[dependency + "_run"]).resolve()
            record = read(run / "record.json")
            if record["stage"] != dependency or record["status"] != "completed" or record["case_id"] != case or record["project"] != str(project):
                raise ValueError("Invalid dependency stage/status/case/project")
            if not finished_run_is_intact(run, record):
                raise ValueError("Dependency was modified")
            inputs["dependencies"][dependency] = {
                "run_id": record["run_id"],
                "report_sha256": record["report_sha256"],
                "input_sha256": record["input_sha256"],
                "perspectives_sha256": record.get("perspectives_sha256", {}),
            }
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    base = Path(output_root).expanduser().absolute() if output_root is not None else Path.home() / "agent-analysis-results"
    project_id = re.sub(r"[^A-Za-z0-9_-]", "-", project.name)[:40] or "project"
    project_id += "-" + hashlib.sha256(os.fsencode(project)).hexdigest()[:10]
    run = base / project_id / case / stage / run_id
    if any(p.is_symlink() for p in [base, *base.parents, run, *run.parents] if p != Path("/")):
        raise ValueError("Symlink output path not allowed")
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    if base.stat().st_mode & 0o077:
        raise ValueError("Output root must be private (mode 0700); select another directory or change permissions explicitly")
    for directory in (base / project_id, base / project_id / case, base / project_id / case / stage):
        directory.mkdir(mode=0o700, exist_ok=True)
    run.mkdir(mode=0o700)
    write(run / "input.json", inputs)
    # start.json remains immutable; record.json is written only on finish.
    write(run / "start.json", {"schema_version":1, "run_id":run_id, "case_id":case, "project":str(project), "output_root":str(base), "stage":stage, "status":"running", "started_at":now(), "input_sha256":digest(run / "input.json")})
    return run


def finish(run, report, status, usage, graph=None, perspectives_dir=None):
    if status not in ("completed", "blocked", "failed"):
        raise ValueError("Invalid finish status")
    run = Path(run).resolve()
    record = read(run / "start.json")
    if (run / "record.json").exists() or (run / "report.txt").exists():
        raise ValueError("Already finished or partially written; use a new run")
    if digest(run / "input.json") != record["input_sha256"]:
        raise ValueError("Input snapshot was modified")
    inputs = read(run / "input.json")
    if status == "completed":
        for path, expected in inputs.get("spec_hashes", {}).items():
            if digest(path) != expected:
                raise ValueError("Specification changed during analysis")
        for stage, dependency in inputs.get("dependencies", {}).items():
            previous = Path(inputs[stage + "_run"])
            previous_record = read(previous / "record.json")
            if (not finished_run_is_intact(previous, previous_record)
                    or previous_record.get("report_sha256") != dependency["report_sha256"]
                    or previous_record.get("input_sha256") != dependency["input_sha256"]
                    or previous_record.get("perspectives_sha256", {}) != dependency.get("perspectives_sha256", {})):
                raise ValueError("Dependency changed during analysis")
    usage_check(usage)
    text = Path(report).read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("Empty report")
    perspective_documents = None
    if record["stage"] == "source" and status == "completed" and inputs["domain"] == "driver":
        if perspectives_dir is None:
            raise ValueError("Completed driver source reports need perspective documents")
        perspective_documents = collect_perspectives(perspectives_dir, run)
    elif perspectives_dir is not None:
        raise ValueError("Perspective documents are only supported for completed driver source reports")
    if record["stage"] == "source" and status == "completed":
        preparation_path = run / "codegraph-preparation.json"
        if not preparation_path.is_file():
            raise ValueError("Source completion needs CodeGraph preparation record")
        preparation = read(preparation_path)
        if preparation.get("status") != "prepared" or preparation.get("source_root") != str(Path(inputs["source_root"]).resolve()):
            raise ValueError("CodeGraph preparation was not successful for source_root")
        record["codegraph_preparation_sha256"] = digest(preparation_path)
        db = Path(inputs["source_root"]).resolve() / ".codegraph" / "codegraph.db"
        if not db.is_file():
            raise ValueError("Source completion needs local CodeGraph DB")
        try:
            with sqlite3.connect("file:" + quote(str(db)) + "?mode=ro", uri=True) as connection:
                connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        except sqlite3.DatabaseError as error:
            raise ValueError("Invalid local CodeGraph DB") from error
        if graph is None or not Path(graph).read_text(encoding="utf-8").strip():
            raise ValueError("Source completion needs CodeGraph evidence")
        record["codegraph_db"] = str(db)
        record["codegraph_evidence_sha256"] = digest(graph)
        with os.fdopen(os.open(run / "codegraph.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
            stream.write(Path(graph).read_text(encoding="utf-8"))
    if perspective_documents is not None:
        target_dir = run / "perspectives"
        target_dir.mkdir(mode=0o700)
        record["perspectives_sha256"] = {}
        for relative, data in perspective_documents.items():
            target = run / relative
            with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
                stream.write(data)
            record["perspectives_sha256"][relative] = digest(target)
    with os.fdopen(os.open(run / "report.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
        stream.write(text)
    record.update(status=status, ended_at=now(), report_sha256=digest(run / "report.txt"), usage=usage)
    record["elapsed_seconds"] = (stamp(record["ended_at"]) - stamp(record["started_at"])).total_seconds()
    write(run / "record.json", record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    command = subs.add_parser("start")
    command.add_argument("--project", required=True)
    command.add_argument("--output-root", help="Defaults to ~/agent-analysis-results on the execution host")
    command.add_argument("--case", required=True)
    command.add_argument("--stage", choices=REQUIRED, required=True)
    command.add_argument("--input", required=True)
    command = subs.add_parser("finish")
    command.add_argument("--run", required=True)
    command.add_argument("--report", required=True)
    command.add_argument("--status", choices=("completed", "blocked", "failed"), required=True)
    command.add_argument("--usage", required=True)
    command.add_argument("--codegraph-evidence")
    command.add_argument("--perspectives-dir", help="Seven Markdown viewpoints for a completed driver source run")
    command = subs.add_parser("usage")
    command.add_argument("--run", required=True)
    command.add_argument("--input", required=True)
    args = parser.parse_args()
    try:
        if args.action == "start":
            print(start(args.project, args.case, args.stage, read(args.input), args.output_root))
        elif args.action == "finish":
            result = finish(args.run, args.report, args.status, read(args.usage), args.codegraph_evidence, args.perspectives_dir)
            print(result["run_id"], result["status"])
        else:
            run = Path(args.run).resolve()
            record = read(run / "record.json")
            data = usage_check(read(args.input))
            revision = run / ("usage-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8] + ".json")
            write(revision, {"run_id":record["run_id"], "recorded_at":now(), "usage":data})
            print(revision)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
