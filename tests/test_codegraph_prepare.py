import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "agent-kit" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


run_tool = module("run")
prepare_tool = module("prepare_codegraph")


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inputs = dict(source_root=str(self.root), source_commit="test", dirty_state="clean",
                           build_config="test", domain="driver", scope="test", kit_revision="test", host_version="test")
        self.run = run_tool.start(self.root, "test", "source", self.inputs, self.root / "private")
        self.calls = []

    def fake(self, args, **kwargs):
        self.calls.append(args[1:])
        self.assertEqual(kwargs["cwd"], self.root)
        self.assertEqual(kwargs["env"]["CODEGRAPH_TELEMETRY"], "0")
        if args[1] == "init":
            db = self.root / ".codegraph" / "codegraph.db"
            db.parent.mkdir(exist_ok=True)
            sqlite3.connect(db).close()
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    def test_missing_db_initializes_once_and_records(self):
        result = prepare_tool.prepare(self.run, executable="codegraph", invoke=self.fake)
        self.assertEqual(result["status"], "prepared")
        self.assertEqual([args[0] for args in self.calls], ["version", "init", "status"])
        self.assertEqual(self.calls[1], ["init", str(self.root), "--local-only"])
        self.assertTrue((self.run / "codegraph-preparation.json").is_file())
        with self.assertRaisesRegex(ValueError, "already attempted"):
            prepare_tool.prepare(self.run, executable="codegraph", invoke=self.fake)

    def test_existing_db_reused_without_init(self):
        db = self.root / ".codegraph" / "codegraph.db"
        db.parent.mkdir()
        sqlite3.connect(db).close()
        result = prepare_tool.prepare(self.run, executable="codegraph", invoke=self.fake)
        self.assertEqual(result["action"], "reuse")
        self.assertEqual([args[0] for args in self.calls], ["version", "status"])

    def test_nonempty_index_without_db_blocks_without_overwrite(self):
        index = self.root / ".codegraph"
        index.mkdir()
        (index / "config.json").write_text("preserve")
        result = prepare_tool.prepare(self.run, executable="codegraph", invoke=self.fake)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual([args[0] for args in self.calls], ["version"])
        self.assertEqual((index / "config.json").read_text(), "preserve")

    def test_missing_cli_blocks_and_records(self):
        with patch.object(prepare_tool.shutil, "which", return_value=None):
            result = prepare_tool.prepare(self.run, invoke=self.fake)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("not installed", result["error"])
        self.assertFalse(self.calls)
        self.assertTrue((self.run / "codegraph-preparation.json").exists())


if __name__ == "__main__":
    unittest.main()
