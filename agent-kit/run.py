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
import subprocess
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
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
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


def source_file(root, relative):
    path = Path(relative)
    if (not path.parts or path.is_absolute() or ".." in path.parts
            or {".git", ".codegraph"}.intersection(path.parts)):
        raise ValueError("Invalid source-relative path: " + relative)
    target = root / path
    if any(p.is_symlink() for p in (target, *target.parents) if p.is_relative_to(root)) or not target.is_file():
        raise ValueError("Source evidence must be an existing regular file without symlinks: " + relative)
    return target


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30,
                          env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"})


def source_snapshot(inputs, selected):
    root = Path(inputs["source_root"])
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("Investigation needs an existing absolute source_root")
    root = root.resolve()
    paths = selected.get("files")
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
        raise ValueError("investigation.files must list the relevant source-relative files")
    preserve = selected.get("preserve_files", False)
    if not isinstance(preserve, bool):
        raise ValueError("preserve_files must be a boolean")
    commit = str(inputs["source_commit"])
    repo = None
    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit):
        base = git(root, "rev-parse", "--show-toplevel")
        if base.returncode == 0:
            repo = Path(os.fsdecode(base.stdout.rstrip(b"\n")))
    files, copies = {}, {}
    for relative in paths:
        target = source_file(root, relative)
        relative = target.relative_to(root).as_posix()
        if relative in files:
            raise ValueError("Duplicate investigation file: " + relative)
        current = digest(target)
        entry = files[relative] = {"sha256": current, "recovery": "unavailable"}
        if repo is not None:
            spec = f"{commit}:{target.relative_to(repo).as_posix()}"
            blob = git(repo, "cat-file", "blob", spec)
            if blob.returncode == 0 and hashlib.sha256(blob.stdout).hexdigest() == current:
                entry.update(recovery="git", git_path=target.relative_to(repo).as_posix())
        if entry["recovery"] == "unavailable" and preserve:
            data = target.read_bytes()
            if hashlib.sha256(data).hexdigest() != current:
                raise ValueError("Source changed during capture: " + relative)
            entry.update(recovery="private-copy", path="evidence/source/" + current)
            copies[current] = data
    return {"schema_version": 1, "source_root": str(root), "git_root": str(repo) if repo else None,
            "commit": commit, "dirty_state": inputs["dirty_state"], "build_config": inputs["build_config"],
            "scope": inputs["scope"], "domain": inputs["domain"], "files": files}, copies


def yocto_reuse_identity(evidence):
    """Pin semantic inputs; do not compare mutable paths or command output."""
    fields = ("status", "target", "package", "recipe_package", "recipe",
              "package_versions", "provenance")
    identity = {key: evidence.get(key) for key in fields}
    for key in ("image", "image_manifest", "rootfs_file", "kernel_config",
                "build_metadata", "build_capture"):
        identity[key + "_sha256"] = (evidence.get(key) or {}).get("sha256")
    identity["candidate_source_hashes"] = {
        path: entry["sha256"] for path, entry in evidence.get("candidate_sources", {}).items()
    }
    return identity


def prior_source(project, path, snapshot):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("Prior source run needs an absolute path")
    path = path.resolve()
    record = read(path / "record.json")
    if record.get("stage") != "source" or record.get("status") != "completed" or record.get("project") != str(project):
        raise ValueError("Prior run must be a completed source run for this project")
    artifacts = {"input.json": record["input_sha256"], "report.txt": record["report_sha256"]}
    for name, field in (("source-manifest.json", "source_manifest_sha256"),
                        ("facts/paths.json", "source_facts_sha256"),
                        ("yocto-evidence.json", "yocto_evidence_sha256")):
        if record.get(field):
            artifacts[name] = record[field]
    for name, expected in artifacts.items():
        if digest(source_file(path, name)) != expected:
            raise ValueError("Prior source artifact was modified: " + name)
    old = read(path / "source-manifest.json") if "source-manifest.json" in artifacts else {}
    old_files = old.get("files", {})
    same = all(old.get(key) == snapshot.get(key) for key in (
        "source_root", "commit", "dirty_state", "build_config", "scope", "domain",
        "yocto_image_sha256", "yocto_identity"))
    same = same and {k: v["sha256"] for k, v in old_files.items()} == {k: v["sha256"] for k, v in snapshot["files"].items()}
    def incomplete(value):
        if isinstance(value, dict):
            return not value or any(incomplete(v) for v in value.values())
        if isinstance(value, list):
            return not value or any(incomplete(v) for v in value)
        return value is None or str(value).strip().lower() in ("", "unknown", "none", "null", "n/a", "未確認", "不明")

    unknown_version = incomplete(old.get("commit")) or incomplete(snapshot.get("commit"))
    unknown_config = not isinstance(snapshot["build_config"], dict) or incomplete(snapshot["build_config"])
    yocto = snapshot.get("yocto_identity")
    unresolved_yocto = yocto is not None and (
        yocto["status"] != "recipe-candidate"
        or any(incomplete(yocto[key]) for key in ("target", "package", "recipe_package", "recipe", "image_manifest_sha256"))
        or yocto["provenance"] == "build-capture-mismatch")
    reuse = "hypothesis-only"
    if not unknown_version and old_files and "facts/paths.json" in artifacts:
        old_recoverable = all(entry["recovery"] != "unavailable" for entry in old_files.values())
        if same and not unknown_config and not unresolved_yocto:
            reuse = "same-inputs"
        elif old_recoverable:
            # References are candidates until the named objects are recovered and verified.
            reuse = "comparison-only"
    return {"path": str(path), "run_id": record["run_id"], "reuse": reuse, "sha256": artifacts}


def check_source_facts(data, snapshot, mode, runtime=None):
    if data.get("schema_version") != 1 or not isinstance(data.get("paths"), list) or not data["paths"]:
        raise ValueError("Source facts need schema_version=1 and paths")
    ids = set()
    for item in data["paths"]:
        for key in ("id", "title", "trigger", "context", "state", "resources", "failure", "stop", "observation"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError("Source path needs " + key)
        if not re.fullmatch(r"[a-z0-9-]+", item["id"]) or item["id"] in ids:
            raise ValueError("Invalid or duplicate source path ID")
        ids.add(item["id"])
        if item.get("certainty") not in ("source-confirmed", "configuration-dependent", "runtime-observed", "unverified"):
            raise ValueError("Invalid source path certainty")
        if item["certainty"] == "runtime-observed" and not item.get("runtime_evidence"):
            raise ValueError("Runtime observation needs evidence")
        if not isinstance(item.get("steps"), list) or not item["steps"]:
            raise ValueError("Source path needs ordered steps")
        for step in item["steps"]:
            if not all(isinstance(step.get(k), str) and step[k].strip() for k in ("from", "to", "label")):
                raise ValueError("Source step needs from/to/label")
            if step.get("kind") not in ("call", "return", "async") or len(step["label"]) > 100:
                raise ValueError("Source step needs valid kind and a concise label")
            ref = step.get("evidence", {})
            lines = (ref.get("start"), ref.get("end"))
            if (ref.get("file") not in snapshot["files"] or any(type(n) is not int for n in lines)
                    or not 1 <= lines[0] <= lines[1]):
                raise ValueError("Source step needs a captured file and valid line range")
    hypotheses = data.get("hypotheses", [])
    if not isinstance(hypotheses, list) or (mode == "incident" and not hypotheses):
        raise ValueError("Incident facts need hypotheses")
    runtime = runtime or {}
    for item in hypotheses:
        if item.get("path_id") not in ids or not all(
                isinstance(item.get(k), str) and item[k].strip() for k in ("candidate", "support", "falsifier", "next_observation")):
            raise ValueError("Hypothesis needs path_id, candidate, support, falsifier and next_observation")
        state = item.get("status")
        if state not in ("candidate", "supported", "refuted", "confirmed"):
            raise ValueError("Invalid hypothesis status")
        if state in ("refuted", "confirmed") and not all(
                isinstance(item.get(k), str) and item[k].strip()
                for k in ("decision_evidence", "discriminating_observation")):
            raise ValueError("Hypothesis decision needs evidence and a discriminating observation")
        if state == "confirmed":
            expected = runtime.get("expected_artifact_sha256")
            observed = runtime.get("observed_artifact_sha256")
            if (mode != "incident" or not expected or expected != observed
                    or item["decision_evidence"] not in runtime.get("evidence", {})):
                raise ValueError("Confirmed cause needs matching runtime artifact and current observation evidence")
    if mode == "incident":
        if data.get("stop_reason") not in ("decision", "evidence-exhausted", "budget-limit"):
            raise ValueError("Incident facts need a stop reason")
        data["incident_resolution"] = "confirmed" if any(
            item["status"] == "confirmed" for item in hypotheses) else "not-confirmed"
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
    snapshot = None
    yocto_evidence = None
    if "investigation" in inputs:
        selected = inputs["investigation"]
        if stage != "source" or not isinstance(selected, dict) or selected.get("mode") not in ("understand", "incident"):
            raise ValueError("Investigation is source-only and needs mode understand or incident")
        if "runtime" in selected:
            runtime = selected["runtime"]
            if selected["mode"] != "incident" or not isinstance(runtime, dict):
                raise ValueError("Runtime evidence requires incident mode")
            for key in ("expected_artifact_sha256", "observed_artifact_sha256"):
                value = runtime.get(key)
                if value is not None and not re.fullmatch(r"[a-f0-9]{64}", value):
                    raise ValueError("Invalid artifact SHA-256: " + key)
            evidence = runtime.get("evidence", {})
            if not isinstance(evidence, dict):
                raise ValueError("Runtime evidence must map IDs to authorized absolute files")
            for ident, filename in evidence.items():
                artifact = Path(filename)
                if not re.fullmatch(r"[a-z0-9-]+", ident) or not artifact.is_absolute() or not artifact.is_file():
                    raise ValueError("Invalid runtime evidence ID or file")
                evidence[ident] = {"path": str(artifact.resolve()), "sha256": digest(artifact)}
        if "yocto_evidence" in selected:
            path = Path(selected["yocto_evidence"])
            if not path.is_absolute():
                raise ValueError("Yocto evidence needs an absolute evidence file path")
            yocto_evidence = read(path)
            if (yocto_evidence.get("schema_version") != 1 or not yocto_evidence.get("status")
                    or not yocto_evidence.get("image", {}).get("sha256")):
                raise ValueError("Expected output of yocto_evidence.py")
        snapshot, copies = source_snapshot(inputs, selected)
        if yocto_evidence is not None:
            for relative, evidence in yocto_evidence.get("candidate_sources", {}).items():
                if snapshot["files"].get(relative, {}).get("sha256") != evidence["sha256"]:
                    raise ValueError("Yocto candidate source not captured or changed: " + relative)
            snapshot["yocto_image_sha256"] = yocto_evidence["image"]["sha256"]
            snapshot["yocto_identity"] = yocto_reuse_identity(yocto_evidence)
        paths = selected.get("prior_runs", [])
        if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
            raise ValueError("prior_runs must list absolute source run paths")
        priors = [prior_source(project, path, snapshot) for path in paths]
        if len({entry["run_id"] for entry in priors}) != len(priors):
            raise ValueError("Duplicate prior source run")
        selected["prior_dependencies"] = priors
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
    record = {"schema_version":1, "run_id":run_id, "case_id":case, "project":str(project), "output_root":str(base), "stage":stage, "status":"running", "started_at":now(), "input_sha256":digest(run / "input.json")}
    if snapshot is not None:
        write(run / "source-manifest.json", snapshot)
        record["source_manifest_sha256"] = digest(run / "source-manifest.json")
        if yocto_evidence is not None:
            write(run / "yocto-evidence.json", yocto_evidence)
            record["yocto_evidence_sha256"] = digest(run / "yocto-evidence.json")
        if copies:
            (run / "evidence").mkdir(mode=0o700)
            (run / "evidence/source").mkdir(mode=0o700)
        for sha, data in copies.items():
            with os.fdopen(os.open(run / "evidence/source" / sha, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
                stream.write(data)
    write(run / "start.json", record)
    return run


def finish(run, report, status, usage, graph=None, source_facts=None):
    if status not in ("completed", "blocked", "failed"):
        raise ValueError("Invalid finish status")
    run = Path(run).resolve()
    record = read(run / "start.json")
    if (run / "record.json").exists() or (run / "report.txt").exists():
        raise ValueError("Already finished or partially written; use a new run")
    if digest(run / "input.json") != record["input_sha256"]:
        raise ValueError("Input snapshot was modified")
    inputs = read(run / "input.json")
    facts = None
    investigation = inputs.get("investigation")
    if source_facts is not None and (not investigation or status != "completed"):
        raise ValueError("--source-facts requires a completed investigation")
    if investigation and status == "completed":
        manifest = source_file(run, "source-manifest.json")
        if digest(manifest) != record["source_manifest_sha256"]:
            raise ValueError("Source manifest was modified")
        snapshot = read(manifest)
        runtime = investigation.get("runtime", {})
        for artifact in runtime.get("evidence", {}).values():
            if digest(artifact["path"]) != artifact["sha256"]:
                raise ValueError("Runtime evidence changed during analysis")
        if record.get("yocto_evidence_sha256") and digest(source_file(run, "yocto-evidence.json")) != record["yocto_evidence_sha256"]:
            raise ValueError("Yocto evidence was modified")
        for path, entry in snapshot["files"].items():
            if digest(source_file(Path(snapshot["source_root"]), path)) != entry["sha256"]:
                raise ValueError("Source changed during analysis: " + path)
            if entry["recovery"] == "private-copy" and digest(source_file(run, entry["path"])) != entry["sha256"]:
                raise ValueError("Private source copy changed: " + path)
        for dependency in investigation["prior_dependencies"]:
            for name, expected in dependency["sha256"].items():
                if digest(source_file(Path(dependency["path"]), name)) != expected:
                    raise ValueError("Prior source artifact changed during analysis: " + name)
        if source_facts is None:
            raise ValueError("Investigation completion needs --source-facts")
        facts = check_source_facts(read(source_facts), snapshot, investigation["mode"], runtime)
        if (run / "facts").exists() or (run / "facts").is_symlink():
            raise ValueError("Reserved facts directory already exists")
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
    if facts is not None:
        (run / "facts").mkdir(mode=0o700)
        write(run / "facts/paths.json", facts)
        record["source_facts_sha256"] = digest(run / "facts/paths.json")
    with os.fdopen(os.open(run / "report.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
        stream.write(text)
    record.update(status=status, ended_at=now(), report_sha256=digest(run / "report.txt"), usage=usage)
    record["elapsed_seconds"] = (stamp(record["ended_at"]) - stamp(record["started_at"])).total_seconds()
    write(run / "record.json", record)
    return record


def recover_source(run, relative, git_root=None):
    run = Path(run).resolve()
    record = read(run / "record.json")
    if record.get("stage") != "source" or record.get("status") != "completed":
        raise ValueError("Source recovery requires a completed source run")
    manifest = source_file(run, "source-manifest.json")
    if digest(manifest) != record.get("source_manifest_sha256"):
        raise ValueError("Source manifest is not pinned by the run")
    data = read(manifest)
    entry = data["files"].get(relative)
    if not entry:
        raise ValueError("File is outside the recorded source scope")
    if entry["recovery"] == "git":
        blob = git(git_root or data["git_root"], "cat-file", "blob", data["commit"] + ":" + entry["git_path"])
        if blob.returncode != 0:
            raise ValueError("Git object unavailable; supply a checkout containing the recorded commit")
        content = blob.stdout
    elif entry["recovery"] == "private-copy":
        content = source_file(run, entry["path"]).read_bytes()
    else:
        raise ValueError("Original source was not preserved")
    if hashlib.sha256(content).hexdigest() != entry["sha256"]:
        raise ValueError("Recovered source hash does not match the run")
    return content


def reusable_source_paths(run, prior_run_id):
    """Return only static path facts from a verified same-inputs dependency."""
    run = Path(run).resolve()
    record = read(run / "start.json")
    if record.get("stage") != "source" or digest(source_file(run, "input.json")) != record["input_sha256"]:
        raise ValueError("Expected an intact source run")
    investigation = read(run / "input.json").get("investigation", {})
    dependency = next((d for d in investigation.get("prior_dependencies", [])
                       if d["run_id"] == prior_run_id), None)
    if dependency is None or dependency["reuse"] != "same-inputs":
        raise ValueError("Static path reuse requires a pinned same-inputs dependency")
    previous = Path(dependency["path"])
    for name, expected in dependency["sha256"].items():
        if digest(source_file(previous, name)) != expected:
            raise ValueError("Prior source artifact changed: " + name)
    data = read(previous / "facts/paths.json")
    fields = ("id", "title", "trigger", "context", "state", "resources", "failure", "stop", "steps", "certainty")
    step_fields = ("from", "to", "kind", "label")
    paths = []
    for item in data["paths"]:
        if item["certainty"] not in ("source-confirmed", "configuration-dependent"):
            continue
        row = {key: item[key] for key in fields if key != "steps"}
        row["steps"] = [{**{key: step[key] for key in step_fields},
                         "evidence": {key: step["evidence"][key] for key in ("file", "start", "end")}}
                        for step in item["steps"]]
        paths.append(row)
    return {"schema_version": 1, "prior_run_id": prior_run_id, "paths": paths}


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
    command.add_argument("--source-facts")
    command = subs.add_parser("source-file", help="Write verified original source to stdout")
    command.add_argument("--run", required=True)
    command.add_argument("--file", required=True)
    command.add_argument("--git-root")
    command = subs.add_parser("prior-static-paths", help="Print reusable static paths without incident conclusions")
    command.add_argument("--run", required=True)
    command.add_argument("--prior-run-id", required=True)
    command = subs.add_parser("usage")
    command.add_argument("--run", required=True)
    command.add_argument("--input", required=True)
    args = parser.parse_args()
    try:
        if args.action == "start":
            print(start(args.project, args.case, args.stage, read(args.input), args.output_root))
        elif args.action == "finish":
            result = finish(args.run, args.report, args.status, read(args.usage), args.codegraph_evidence, args.source_facts)
            print(result["run_id"], result["status"])
        elif args.action == "source-file":
            import sys
            sys.stdout.buffer.write(recover_source(args.run, args.file, args.git_root))
        elif args.action == "prior-static-paths":
            print(json.dumps(reusable_source_paths(args.run, args.prior_run_id), ensure_ascii=False, indent=2))
        else:
            run = Path(args.run).resolve()
            record = read(run / "record.json")
            data = usage_check(read(args.input))
            revision = run / ("usage-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8] + ".json")
            write(revision, {"run_id":record["run_id"], "recorded_at":now(), "usage":data})
            print(revision)
    except (ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
