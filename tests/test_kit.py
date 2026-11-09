import importlib.util
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class KitTests(unittest.TestCase):
    def test_validate(self):
        self.assertEqual(module("validate").validate(), 5)

    def test_reproducible(self):
        first = module("render").outputs()
        self.assertEqual(first, module("render").outputs())
        for path, content in first.items():
            self.assertEqual((ROOT / path).read_text(encoding="utf-8"), content)

    def test_install_dry_plan(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            self.assertGreater(len(module("install").plan(target)), 10)
            self.assertEqual(list(target.iterdir()), [])

    def test_existing_instruction_conflict(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)
            (target / "AGENTS.md").write_text("User-owned instructions", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Conflicts"):
                module("install").plan(target)
            self.assertEqual((target / "AGENTS.md").read_text(), "User-owned instructions")
            self.assertEqual(len(list(target.iterdir())), 1)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as outside:
            target = Path(folder)
            (target / ".github").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "Symlink"):
                module("install").plan(target)

    def test_install_apply_and_idempotence(self):
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run([sys.executable, str(ROOT / "tools/install.py"), "--target", folder, "--apply"],
                           check=True, capture_output=True, text=True)
            target = Path(folder)
            self.assertEqual((target / "AGENTS.md").read_bytes(), (ROOT / "AGENTS.md").read_bytes())
            self.assertTrue((target / ".codex/agents/evidence-reviewer.toml").exists())
            for name in ("render_source_report.py", "export_run.py"):
                script = target / "tools" / name
                self.assertEqual(script.read_bytes(), (ROOT / "tools" / name).read_bytes())
                subprocess.run([sys.executable, str(script), "--help"],
                               check=True, capture_output=True, text=True)
            self.assertEqual(module("install").plan(target), [])


if __name__ == "__main__":
    unittest.main()
