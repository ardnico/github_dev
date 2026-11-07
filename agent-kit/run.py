"""Record staged analysis outputs and observed usage; no LLM/tool execution."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
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


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


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


def start(project, case, stage, inputs):
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
            if digest(run / "report.txt") != record["report_sha256"] or digest(run / "input.json") != record["input_sha256"]:
                raise ValueError("Dependency was modified")
            inputs["dependencies"][dependency] = {"run_id":record["run_id"], "report_sha256":record["report_sha256"], "input_sha256":record["input_sha256"]}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    run = project / "local-results" / case / stage / run_id
    if any(p.is_symlink() for p in [run, *run.parents] if p != project):
        raise ValueError("Symlink output path not allowed")
    run.mkdir(parents=True, exist_ok=False)
    write(run / "input.json", inputs)
    # start.json remains immutable; record.json is written only on finish.
    write(run / "start.json", {"schema_version":1, "run_id":run_id, "case_id":case, "project":str(project), "stage":stage, "status":"running", "started_at":now(), "input_sha256":digest(run / "input.json")})
    return run


def finish(run, report, status, usage, graph=None):
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
            if digest(previous / "report.txt") != dependency["report_sha256"] or digest(previous / "input.json") != dependency["input_sha256"]:
                raise ValueError("Dependency changed during analysis")
    usage_check(usage)
    text = Path(report).read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("Empty report")
    if record["stage"] == "source" and status == "completed":
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
        with (run / "codegraph.txt").open("x", encoding="utf-8") as stream:
            stream.write(Path(graph).read_text(encoding="utf-8"))
    with (run / "report.txt").open("x", encoding="utf-8") as stream:
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
    command.add_argument("--case", required=True)
    command.add_argument("--stage", choices=REQUIRED, required=True)
    command.add_argument("--input", required=True)
    command = subs.add_parser("finish")
    command.add_argument("--run", required=True)
    command.add_argument("--report", required=True)
    command.add_argument("--status", choices=("completed", "blocked", "failed"), required=True)
    command.add_argument("--usage", required=True)
    command.add_argument("--codegraph-evidence")
    command = subs.add_parser("usage")
    command.add_argument("--run", required=True)
    command.add_argument("--input", required=True)
    args = parser.parse_args()
    try:
        if args.action == "start":
            print(start(args.project, args.case, args.stage, read(args.input)))
        elif args.action == "finish":
            result = finish(args.run, args.report, args.status, read(args.usage), args.codegraph_evidence)
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
