import importlib.util
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

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
        (self.root / "driver.c").write_text("int driver(void) { return 0; }\n")
        self.cli = self.root / "codegraph-bin"
        self.cli.write_text("#!/bin/sh\nexit 1\n")
        self.cli.chmod(0o700)
        self.inputs = dict(source_root=str(self.root), source_commit="test", dirty_state="clean",
                           build_config="test", domain="driver", scope={"resolved_files": ["driver.c"]}, kit_revision="test", host_version="test")
        self.run = run_tool.start(self.root, "test", "source", self.inputs, self.root / "private")
        self.calls = []

    def fake(self, args, **kwargs):
        self.calls.append(args[1:])
        self.assertEqual(kwargs["cwd"], self.root)
        self.assertEqual(kwargs["env"]["CODEGRAPH_TELEMETRY"], "0")
        self.assertEqual(kwargs["env"]["CODEGRAPH_DIR"], ".codegraph-colbymchenry")
        if args[1] == "init":
            db = self.root / ".codegraph-colbymchenry" / "codegraph.db"
            db.parent.mkdir(exist_ok=True)
            self.make_db(db)
        if args[1] == "status":
            payload = self.status()
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="1.6.2", stderr="")

    def make_db(self, db):
        with sqlite3.connect(db) as connection:
            connection.execute("CREATE TABLE files (path TEXT, content_hash TEXT, errors TEXT)")
            connection.execute("CREATE TABLE nodes (id TEXT)")
            connection.execute("CREATE TABLE edges (id TEXT)")
            connection.execute("INSERT INTO files VALUES (?, ?, ?)", ("driver.c", hashlib.sha256((self.root / "driver.c").read_bytes()).hexdigest(), None))

    def status(self):
        return {"initialized": (self.root / ".codegraph-colbymchenry/codegraph.db").is_file(),
                "version": "1.6.2", "projectPath": str(self.root),
                "indexPath": str(self.root / ".codegraph-colbymchenry"), "fileCount": 1,
                "pendingChanges": {"added": 0, "modified": 0, "removed": 0}, "worktreeMismatch": None,
                "index": {"state": "complete", "builtWithVersion": "1.6.2", "builtWithExtractionVersion": 27,
                          "currentExtractionVersion": 27, "reindexRecommended": False, "pendingRefs": 0}}

    def test_missing_db_initializes_once_and_records(self):
        result = prepare_tool.prepare(self.run, executable=str(self.cli), invoke=self.fake)
        self.assertEqual(result["status"], "prepared")
        self.assertEqual([args[0] for args in self.calls], ["version", "status", "init", "status"])
        self.assertEqual(self.calls[2], ["init", str(self.root), "--yes"])
        self.assertEqual(result["verified_files"][0]["path"], "driver.c")
        self.assertTrue((self.run / "codegraph-preparation.json").is_file())
        with self.assertRaisesRegex(ValueError, "already attempted"):
            prepare_tool.prepare(self.run, executable=str(self.cli), invoke=self.fake)

    def test_existing_db_reused_without_init(self):
        db = self.root / ".codegraph-colbymchenry" / "codegraph.db"
        db.parent.mkdir()
        self.make_db(db)
        result = prepare_tool.prepare(self.run, executable=str(self.cli), invoke=self.fake)
        self.assertEqual(result["action"], "reuse")
        self.assertEqual([args[0] for args in self.calls], ["version", "status", "status"])

    def test_nonempty_index_without_db_blocks_without_overwrite(self):
        index = self.root / ".codegraph-colbymchenry"
        index.mkdir()
        (index / "config.json").write_text("preserve")
        result = prepare_tool.prepare(self.run, executable=str(self.cli), invoke=self.fake)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual([args[0] for args in self.calls], ["version", "status"])
        self.assertEqual((index / "config.json").read_text(), "preserve")

    def test_missing_cli_blocks_and_records(self):
        result = prepare_tool.prepare(self.run, invoke=self.fake)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("--codegraph-bin", result["error"])
        self.assertFalse(self.calls)
        self.assertTrue((self.run / "codegraph-preparation.json").exists())

    def test_other_codegraph_with_existing_db_is_rejected_without_writes(self):
        db = self.root / ".codegraph-colbymchenry/codegraph.db"
        db.parent.mkdir()
        self.make_db(db)
        before = db.read_bytes()

        def other(args, **kwargs):
            self.calls.append(args[1:])
            if args[1] == "status":
                payload = {"schemaVersion": 1, "root": str(self.root), "initialized": False,
                           "manifestPath": str(db.parent / "manifest.json"), "suggestedNextCommand": "codegraph init"}
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")
            return subprocess.CompletedProcess(args, 0, stdout="3.1.3", stderr="")

        result = prepare_tool.prepare(self.run, executable=str(self.cli), invoke=other)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Unsupported CodeGraph CLI version", result["error"])
        self.assertEqual([args[0] for args in self.calls], ["version"])
        self.assertEqual(db.read_bytes(), before)

    def test_expected_cli_rejects_unrecognized_existing_db(self):
        db = self.root / ".codegraph-colbymchenry/codegraph.db"
        db.parent.mkdir()
        self.make_db(db)

        def no_index(args, **kwargs):
            self.calls.append(args[1:])
            if args[1] == "status":
                payload = dict(self.status(), initialized=False)
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")
            return subprocess.CompletedProcess(args, 0, stdout="1.6.2", stderr="")

        result = prepare_tool.prepare(self.run, executable=str(self.cli), invoke=no_index)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("does not recognize", result["error"])
        self.assertEqual([args[0] for args in self.calls], ["version", "status"])

    def test_foreign_default_directory_is_preserved(self):
        foreign = self.root / ".codegraph"
        foreign.mkdir()
        (foreign / "manifest.json").write_text("foreign")
        result = prepare_tool.prepare(self.run, executable=str(self.cli), invoke=self.fake)
        self.assertEqual(result["status"], "prepared")
        self.assertEqual((foreign / "manifest.json").read_text(), "foreign")
        self.assertEqual(result["db"], str(self.root / ".codegraph-colbymchenry/codegraph.db"))

    def test_stale_index_blocks(self):
        db = self.root / ".codegraph-colbymchenry/codegraph.db"
        db.parent.mkdir()
        self.make_db(db)

        def stale(args, **kwargs):
            if args[1] == "status":
                value = self.status()
                value["index"]["reindexRecommended"] = True
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(value), stderr="")
            return self.fake(args, **kwargs)

        result = prepare_tool.prepare(self.run, executable=str(self.cli), invoke=stale)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("reindex", result["error"])
        self.assertNotIn("init", [args[0] for args in self.calls])

    def test_source_hash_mismatch_blocks(self):
        db = self.root / ".codegraph-colbymchenry/codegraph.db"
        db.parent.mkdir()
        self.make_db(db)
        (self.root / "driver.c").write_text("changed")
        result = prepare_tool.prepare(self.run, executable=str(self.cli), invoke=self.fake)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("differs", result["error"])

    def test_scope_file_not_indexed_blocks(self):
        db = self.root / ".codegraph-colbymchenry/codegraph.db"
        db.parent.mkdir()
        self.make_db(db)
        with sqlite3.connect(db) as connection:
            connection.execute("DELETE FROM files")
        result = prepare_tool.prepare(self.run, executable=str(self.cli), invoke=self.fake)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("absent from CodeGraph", result["error"])

    def test_parse_error_blocks(self):
        db = self.root / ".codegraph-colbymchenry/codegraph.db"
        db.parent.mkdir()
        self.make_db(db)
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE files SET errors=?", ('["parse failed"]',))
        result = prepare_tool.prepare(self.run, executable=str(self.cli), invoke=self.fake)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("parse errors", result["error"])

    def test_unexpected_cli_version_blocks_before_init(self):
        def newer(args, **kwargs):
            self.calls.append(args[1:])
            return subprocess.CompletedProcess(args, 0, stdout="1.7.0\n", stderr="")

        result = prepare_tool.prepare(self.run, executable=str(self.cli), invoke=newer)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual([args[0] for args in self.calls], ["version"])
        self.assertFalse((self.root / ".codegraph-colbymchenry").exists())

    def test_other_index_path_blocks(self):
        def wrong(args, **kwargs):
            if args[1] == "status":
                value = self.status()
                value["indexPath"] = str(self.root / ".codegraph")
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(value), stderr="")
            return self.fake(args, **kwargs)

        result = prepare_tool.prepare(self.run, executable=str(self.cli), invoke=wrong)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("another project or index", result["error"])


if __name__ == "__main__":
    unittest.main()
