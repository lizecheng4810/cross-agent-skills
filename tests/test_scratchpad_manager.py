import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "cross-agent-scratchpad-skill" / "工具" / "临时脚本管家.py"
SPEC = importlib.util.spec_from_file_location("scratchpad_manager", TOOL_PATH)
scratchpad_manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scratchpad_manager)


class ScratchpadManagerTests(unittest.TestCase):
    def test_help_output_is_valid_utf8_when_captured(self):
        env = os.environ.copy()
        env.pop("PYTHONIOENCODING", None)
        env["PYTHONUTF8"] = "0"
        result = subprocess.run(
            [sys.executable, str(TOOL_PATH), "--help"],
            capture_output=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("临时脚本管家", result.stdout.decode("utf-8"))

    @unittest.skipUnless(shutil.which("git"), "Git CLI is unavailable")
    def test_git_tracking_detection_supports_linked_worktrees(self):
        with TemporaryDirectory() as temp:
            base = Path(temp) / "repo"
            linked = Path(temp) / "linked-worktree"
            base.mkdir()

            def git(*args):
                return subprocess.run(
                    ["git", "-C", str(base), *args],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

            subprocess.run(
                ["git", "init", str(base)], check=True,
                capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            git("config", "user.name", "Memory Skill Test")
            git("config", "user.email", "memory-skill-test@example.invalid")
            tracked = base / "test_helper.py"
            tracked.write_text("VALUE = 1\n", encoding="utf-8")
            git("add", "test_helper.py")
            git("commit", "-m", "add tracked helper")

            self.assertFalse(scratchpad_manager.git_untracked(str(base), str(tracked)))
            git("worktree", "add", "--detach", str(linked), "HEAD")
            self.assertTrue((linked / ".git").is_file())
            linked_file = linked / "test_helper.py"
            self.assertFalse(scratchpad_manager.git_untracked(str(linked), str(linked_file)))

    @unittest.skipUnless(shutil.which("git"), "Git CLI is unavailable")
    def test_git_tracking_detection_handles_unicode_workspace_paths(self):
        with TemporaryDirectory() as temp:
            repo = Path(temp) / "中文工作区"
            repo.mkdir()
            subprocess.run(
                ["git", "init", str(repo)], check=True,
                capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            tracked = repo / "helper.py"
            tracked.write_text("VALUE = 1\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(repo), "add", "helper.py"], check=True,
                capture_output=True, text=True, encoding="utf-8", errors="replace"
            )

            self.assertEqual(
                os.path.normcase(scratchpad_manager.git_repo_root(str(repo))),
                os.path.normcase(str(repo.resolve())),
            )
            self.assertFalse(scratchpad_manager.git_untracked(str(repo), str(tracked)))


if __name__ == "__main__":
    unittest.main()
