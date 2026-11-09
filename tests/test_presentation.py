import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import os
import stat
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


renderer = module("render_source_report")
exporter = module("export_run")


class PresentationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.run = self.base / "run"
        self.run.mkdir()
        (self.run / "report.txt").write_text("Source <script>alert(1)</script>\nProbe: main.c:12", encoding="utf-8")
        (self.run / "input.json").write_text(json.dumps({"source_commit": "abc123"}))
        (self.run / "record.json").write_text(json.dumps({
            "stage": "source", "status": "completed", "run_id": "run-test",
            "report_sha256": renderer.digest(self.run / "report.txt"),
            "input_sha256": renderer.digest(self.run / "input.json"),
        }))
        self.visuals = self.base / "visuals-input.json"
        self.data = {"schema_version": 1, "title": "Test driver",
                     "fingerprint": [{"axis": "IRQ", "observed": "NAPI", "comparison": "uncompared", "evidence": "main.c:12"}],
                     "variants": [{"condition": "CONFIG_X", "behavior": "Enable", "evidence": "main.c:34"}],
                     "sequences": [{"id": "irq", "title": "IRQ flow", "participants": [
                         {"id": "irq", "label": "IRQ", "context": "hard IRQ"},
                         {"id": "napi", "label": "NAPI", "context": "softirq"}],
                         "messages": [{"from": "irq", "to": "napi", "kind": "async", "label": "schedule", "evidence": "main.c:12"}]}]}
        self.visuals.write_text(json.dumps(self.data))

    def test_render_is_offline_escaped_and_traceable(self):
        output = renderer.render(self.run, self.visuals)
        page = output.read_text()
        self.assertIn("<svg", page)
        self.assertIn("main.c:12", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertNotIn("https://cdn", page)
        self.assertEqual(json.loads((self.run / "presentation.json").read_text())["html_sha256"], renderer.digest(output))
        with self.assertRaisesRegex(ValueError, "already exists"):
            renderer.render(self.run, self.visuals)

    def test_difference_requires_baseline(self):
        self.data["fingerprint"][0]["comparison"] = "different"
        self.visuals.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError, "baseline"):
            renderer.render(self.run, self.visuals)
        self.assertFalse((self.run / "report.html").exists())

    def test_tampered_report_rejected(self):
        (self.run / "report.txt").write_text("changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            renderer.render(self.run, self.visuals)

    def test_export_deduplicates_and_preserves_alias(self):
        renderer.render(self.run, self.visuals)
        (self.run / "draft.txt").write_bytes((self.run / "report.txt").read_bytes())
        (self.run / "codegraph.txt").write_text("queries")
        (self.run / "codegraph-evidence.txt").write_text("queries")
        target = self.base / "bundle.zip"
        exporter.export(self.run, target)
        with zipfile.ZipFile(target) as bundle:
            names = bundle.namelist()
            self.assertIn("reader/report.html", names)
            self.assertIn("evidence/codegraph.txt", names)
            self.assertNotIn("draft.txt", names)
            self.assertNotIn("codegraph-evidence.txt", names)
            manifest = json.loads(bundle.read("bundle-manifest.json"))
            self.assertEqual(manifest["aliases"]["codegraph-evidence.txt"], "evidence/codegraph.txt")
            self.assertEqual(manifest["source_paths"]["reader/report.html"], "report.html")
            self.assertIn("draft.txt", manifest["omitted_work_files"])

    def test_export_is_private_during_write_and_removes_partial_file(self):
        target = self.base / "partial.zip"
        original = os.umask(0o022)
        try:
            def fail_after_open(stream, *args, **kwargs):
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                raise RuntimeError("simulated archive failure")

            with patch.object(exporter.zipfile, "ZipFile", side_effect=fail_after_open):
                with self.assertRaisesRegex(RuntimeError, "simulated archive failure"):
                    exporter.export(self.run, target)
        finally:
            os.umask(original)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
