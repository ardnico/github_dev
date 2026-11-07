import importlib.util
from pathlib import Path
import tempfile
import sqlite3
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "agent-kit/run.py"
spec = importlib.util.spec_from_file_location("run_recorder", MODULE)
recorder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recorder)
UNKNOWN = {"coverage": "unavailable", "missing_reason": "test host has no telemetry", "events": []}


class RunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.draft = self.root / "draft.txt"
        self.draft.write_text("Synthetic test report", encoding="utf-8")
        self.base = dict(scope="test", kit_revision="test-sha", host_version="unittest")

    def start(self, stage="other", **extra):
        inputs = dict(self.base, **extra)
        if stage == "other":
            inputs["task"] = "test"
        return recorder.start(self.root, "test-case", stage, inputs, self.root / "private-results")

    def source(self):
        return self.start("source", source_root=str(self.root), source_commit="test", dirty_state="clean", build_config="test", domain="driver")

    def finish(self, run, status="completed", graph=None):
        return recorder.finish(run, self.draft, status, UNKNOWN, graph)

    def test_output_and_no_overwrite(self):
        run = self.start()
        self.assertEqual(run.parts[-3], "test-case")
        self.assertEqual(run.parents[3].name, "private-results")
        result = self.finish(run)
        self.assertGreaterEqual(result["elapsed_seconds"], 0)
        self.assertEqual(result["usage"]["coverage"], "unavailable")
        self.assertEqual((run / "report.txt").read_text(), self.draft.read_text())
        with self.assertRaises(ValueError):
            self.finish(run)

    def test_source_evidence_required_and_blocked_allowed(self):
        run = self.source()
        with self.assertRaisesRegex(ValueError, "CodeGraph"):
            self.finish(run)
        self.assertEqual(self.finish(run, "blocked")["status"], "blocked")

    def test_input_tampering_rejected(self):
        run = self.start()
        (run / "input.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "snapshot"):
            self.finish(run)

    def test_spec_original_changed(self):
        document = self.root / "spec.txt"
        document.write_text("requirement")
        run = self.start("spec", spec_id="S", spec_revision="1", spec_files=[str(document)], domain="mw")
        document.write_text("changed")
        with self.assertRaisesRegex(ValueError, "Specification changed"):
            self.finish(run)
        self.finish(run, "blocked")

    def test_compare_dependencies_and_tampering(self):
        source = self.source()
        db = self.root / ".codegraph" / "codegraph.db"
        db.parent.mkdir()
        sqlite3.connect(db).close()
        recorder.write(source / "codegraph-preparation.json", {"status":"prepared", "source_root":str(self.root.resolve())})
        self.finish(source, graph=self.draft)  # Synthetic fixture, not a real CodeGraph run.
        document = self.root / "spec.txt"
        document.write_text("requirement")
        spec_run = self.start("spec", spec_id="S", spec_revision="1", spec_files=[str(document)], domain="driver")
        self.finish(spec_run)
        compare = self.start("compare", source_run=str(source), spec_run=str(spec_run), domain="driver")
        (source / "report.txt").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "Dependency changed"):
            self.finish(compare)
        with self.assertRaisesRegex(ValueError, "modified"):
            self.start("compare", source_run=str(source), spec_run=str(spec_run), domain="driver")

    def test_incomplete_dependency_rejected(self):
        source = self.source()
        self.finish(source, "blocked")
        with self.assertRaisesRegex(ValueError, "dependency"):
            self.start("compare", source_run=str(source), spec_run=str(source), domain="driver")

    def test_empty_usage_is_not_complete(self):
        with self.assertRaises(ValueError):
            recorder.usage_check(dict(UNKNOWN, coverage="complete"))
        with self.assertRaises(ValueError):
            recorder.usage_check({"coverage": "unavailable", "events": []})

    def test_invalid_path_and_missing_input(self):
        with self.assertRaises(ValueError):
            recorder.start(self.root, "../escape", "other", dict(self.base, task="test"))
        with self.assertRaises(ValueError):
            recorder.start(self.root, "case", "source", self.base)

    def test_default_home_and_project_separation(self):
        home = self.root / "home"
        home.mkdir(mode=0o700)
        with patch.object(Path, "home", return_value=home):
            run = recorder.start(self.root, "test-case", "other", dict(self.base, task="test"))
        self.assertTrue(run.is_relative_to(home / "agent-analysis-results"))
        self.assertFalse(run.is_relative_to(self.root / "local-results"))
        self.assertEqual(recorder.read(run / "start.json")["project"], str(self.root.resolve()))
        self.assertEqual(run.stat().st_mode & 0o777, 0o700)
        self.assertEqual((run / "input.json").stat().st_mode & 0o777, 0o600)

    def test_reject_shared_output_root(self):
        shared = self.root / "shared"
        shared.mkdir(mode=0o755)
        with self.assertRaisesRegex(ValueError, "private"):
            recorder.start(self.root, "test-case", "other", dict(self.base, task="test"), shared)


if __name__ == "__main__":
    unittest.main()
