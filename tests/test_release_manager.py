import contextlib
import importlib.util
import io
import shutil
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "cross-agent-dev-workflow-skill" / "工具" / "发布管家.py"
SPEC = importlib.util.spec_from_file_location("release_manager", TOOL_PATH)
release_manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_manager)


class ReleaseManagerTests(unittest.TestCase):
    def test_missing_package_blocks_release(self):
        with tempfile.TemporaryDirectory() as temp:
            suite = Path(temp)
            shutil.copyfile(ROOT / "LICENSE", suite / "LICENSE")
            (suite / "README.md").write_text("\n".join(release_manager.SUITE_SKILLS), encoding="utf-8")
            for name in release_manager.SUITE_SKILLS:
                shutil.copytree(
                    ROOT / name,
                    suite / name,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(release_manager.cmd_release_check(str(suite)), 1)
            self.assertIn("发布检查要求三个技能包全部就位", output.getvalue())
            self.assertIn("存在必须修复项", output.getvalue())

    def test_packages_include_matching_licenses_and_exact_source_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            suite = Path(temp)
            shutil.copyfile(ROOT / "LICENSE", suite / "LICENSE")
            (suite / "README.md").write_text("\n".join(release_manager.SUITE_SKILLS), encoding="utf-8")
            for name in release_manager.SUITE_SKILLS:
                shutil.copytree(
                    ROOT / name,
                    suite / name,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
                self.assertEqual(
                    release_manager.cmd_pack(str(suite / name)),
                    0,
                )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(release_manager.cmd_release_check(str(suite)), 0)
            self.assertIn("含 LICENSE", output.getvalue())

            broken_zip = suite / (release_manager.SUITE_SKILLS[0] + ".zip")
            broken_zip.write_bytes(b"not a zip archive")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(release_manager.cmd_release_check(str(suite)), 1)
            self.assertIn("无法读取或验证", output.getvalue())


if __name__ == "__main__":
    unittest.main()
