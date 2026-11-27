import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent-kit"))
import run
import yocto_evidence


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.src = self.base / "src"
        self.src.mkdir()
        self.code = self.src / "driver.c"
        self.code.write_text("static void receive(void) {}\n")
        db = self.src / ".codegraph" / "codegraph.db"
        db.parent.mkdir()
        with sqlite3.connect(db) as conn:
            conn.execute("create table fixture (id integer)")
        self.report = self.base / "report"
        self.report.write_text("test report")
        self.graph = self.base / "graph"
        self.graph.write_text("test graph")
        self.facts_path = self.base / "facts-input.json"
        self.facts = {
            "schema_version": 1, "paths": [{
                "id": "rx", "title": "RX <test>", "trigger": "interrupt", "context": "irq",
                "state": "active", "resources": "buffer", "failure": "error", "stop": "disabled",
                "observation": "counter", "certainty": "source-confirmed", "steps": [
                    {"from": "IRQ", "to": "NAPI", "kind": "async", "label": "wake",
                     "evidence": {"file": "driver.c", "start": 1, "end": 1}}]}],
            "hypotheses": [{"path_id": "rx", "candidate": "no wake", "support": "source",
                           "falsifier": "wake observed", "next_observation": "counter"}]}
        self.inputs = {"source_root": str(self.src), "source_commit": "synthetic-v1", "dirty_state": "clean",
                       "build_config": {"mach": "test"}, "scope": "rx", "domain": "driver",
                       "kit_revision": "test", "host_version": "test",
                       "investigation": {"mode": "incident", "files": ["driver.c"], "preserve_files": True}}

    def start(self):
        result = run.start(self.src, "case", "source", self.inputs, self.base / "results")
        run.write(result / "codegraph-preparation.json", {"status": "prepared", "source_root": str(self.src)})
        return result

    def finish(self, result):
        self.facts_path.write_text(json.dumps(self.facts))
        return run.finish(result, self.report, "completed",
                          {"coverage": "unavailable", "missing_reason": "fixture", "events": []},
                          self.graph, self.facts_path)

    def test_reuse_change_and_tampering(self):
        first = self.start()
        self.finish(first)
        self.inputs["investigation"]["prior_runs"] = [str(first)]
        same = self.start()
        self.assertEqual(run.read(same / "input.json")["investigation"]["prior_dependencies"][0]["reuse"], "same-inputs")
        self.code.write_text("changed\n")
        other = self.start()
        self.assertEqual(run.read(other / "input.json")["investigation"]["prior_dependencies"][0]["reuse"], "comparison-only")
        with self.assertRaisesRegex(ValueError, "Source changed"):
            self.finish(same)
        (first / "facts/paths.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "modified"):
            self.start()

    def test_private_recovery_html_and_export(self):
        first = self.start()
        self.finish(first)
        self.code.unlink()
        self.assertEqual(run.recover_source(first, "driver.c"), b"static void receive(void) {}\n")
        page = load_tool("render_source_report").render(first).read_text()
        self.assertIn("RX &lt;test&gt;", page)
        self.assertIn("wake observed", page)
        self.assertIn("driver.c:1-1", page)
        archive = self.base / "export.zip"
        load_tool("export_run").export(first, archive)
        with zipfile.ZipFile(archive) as stream:
            self.assertIn("evidence/facts/paths.json", stream.namelist())
            self.assertFalse(any(name.startswith("evidence/evidence/source/") for name in stream.namelist()))

    def test_git_recovery_ignores_current_worktree(self):
        def git(*args):
            return subprocess.check_output(["git", "-C", str(self.src), *args], stderr=subprocess.DEVNULL).decode().strip()
        git("init")
        git("add", "driver.c")
        git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture")
        self.inputs["source_commit"] = git("rev-parse", "HEAD")
        self.inputs["investigation"]["preserve_files"] = False
        first = self.start()
        self.finish(first)
        self.code.write_text("different\n")
        self.assertEqual(run.read(first / "source-manifest.json")["files"]["driver.c"]["recovery"], "git")
        self.assertEqual(run.recover_source(first, "driver.c"), b"static void receive(void) {}\n")

    def test_unpreserved_and_invalid_facts(self):
        self.inputs["investigation"]["preserve_files"] = False
        first = self.start()
        self.facts["paths"][0]["steps"][0]["evidence"]["file"] = "not-recorded"
        with self.assertRaisesRegex(ValueError, "captured file"):
            self.finish(first)
        self.facts["paths"][0]["steps"][0]["evidence"]["file"] = "driver.c"
        self.finish(first)
        with self.assertRaisesRegex(ValueError, "not preserved"):
            run.recover_source(first, "driver.c")

    def test_path_escape_rejected(self):
        self.inputs["investigation"]["files"] = ["../report"]
        with self.assertRaisesRegex(ValueError, "Invalid source-relative path"):
            self.start()

    def test_yocto_resolves_only_installed_owner_and_records_capture_match(self):
        image, manifest, capture = (self.base / name for name in ("image.wic", "image.manifest", "capture.json"))
        image.write_bytes(b"image")
        manifest.write_text("foo test 1.0\n")

        def mock_query(args, **kwargs):
            result = "not-installed: /usr/sbin/foo\nfoo: /usr/sbin/foo\n" if args[3] == "find-path" else "foo-recipe\n"
            return subprocess.CompletedProcess(args, 0, result, "")

        args = (self.base, self.base, image, manifest, self.base, "/usr/sbin/foo")
        options = {"patched_root": self.src, "source_files": ["driver.c"]}
        with patch.object(yocto_evidence.subprocess, "run", side_effect=mock_query):
            evidence = yocto_evidence.resolve(*args, **options)
            self.assertEqual(evidence["recipe"], "foo-recipe")
            self.assertEqual(evidence["provenance"], "unverified")
            capture.write_text(json.dumps(evidence))
            matched = yocto_evidence.resolve(*args, **options, build_capture=capture)
            self.assertEqual(matched["provenance"], "matches-build-capture")
            self.inputs["investigation"]["yocto_evidence"] = str(capture)
            first = self.start()
            self.assertEqual(run.read(first / "yocto-evidence.json"), evidence)
            self.finish(first)
            self.code.write_text("other version")
            different = yocto_evidence.resolve(*args, **options, build_capture=capture)
            self.assertEqual(different["provenance"], "build-capture-mismatch")
            with self.assertRaisesRegex(ValueError, "candidate source"):
                self.start()
            manifest.write_text("foo test 1.0\nnot-installed test 1.0\n")
            self.assertEqual(yocto_evidence.resolve(*args)["status"], "package-ambiguous")
