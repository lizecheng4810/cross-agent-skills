import contextlib
import importlib.util
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "cross-agent-memory-skill" / "工具" / "记忆管家.py"
SPEC = importlib.util.spec_from_file_location("memory_manager", TOOL_PATH)
memory_manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(memory_manager)


class MemoryManagerTests(unittest.TestCase):
    def test_new_layer_defaults_to_route_and_handoff_files(self):
        with TemporaryDirectory() as temp:
            target = Path(temp)
            args = SimpleNamespace(target=str(target), 层="1", 通用=False, 完整模板=False)
            with contextlib.redirect_stdout(io.StringIO()):
                memory_manager.cmd_build(args)
            layer = target / "记忆第一层"
            self.assertTrue((layer / "0_索引.md").is_file())
            self.assertTrue((layer / "5_代办.md").is_file())
            self.assertFalse((layer / "1_项目架构.md").exists())

    def test_full_template_remains_available_for_legacy_workflows(self):
        with TemporaryDirectory() as temp:
            target = Path(temp)
            args = SimpleNamespace(target=str(target), 层="1", 通用=False, 完整模板=True)
            with contextlib.redirect_stdout(io.StringIO()):
                memory_manager.cmd_build(args)
            layer = target / "记忆第一层"
            self.assertTrue(all((layer / name).is_file() for name in memory_manager.CORE_FILES))

    def test_fast_takeover_selects_target_ancestors_not_siblings(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self._make_layer(root, "记忆第一层", "root")
            target = root / "project-a"
            sibling = root / "project-b"
            target.mkdir()
            sibling.mkdir()
            self._make_layer(target, "记忆第二层", "target")
            self._make_layer(sibling, "记忆第二层", "sibling")
            args = SimpleNamespace(workspace=str(root), scope=str(target), by="test", full_audit=False)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                memory_manager.cmd_takeover(args)
            text = output.getvalue()
            self.assertIn("project-a/记忆第二层", text)
            self.assertNotIn("project-b/记忆第二层", text)
            self.assertIn("快速模式不扫描兄弟模块", text)

    def test_full_check_finds_candidates_beyond_three_directory_levels(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            deep = root / "one" / "two" / "three" / "four" / "independent-module"
            deep.mkdir(parents=True)
            (deep / "README.md").write_text("module", encoding="utf-8")
            args = SimpleNamespace(workspace=str(root), scope="", max_depth=0)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                memory_manager.cmd_check(args)
            self.assertIn("independent-module", output.getvalue())

    def test_full_check_obeys_root_index_exception_paths(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            memory = root / "记忆第一层"
            memory.mkdir()
            (memory / "0_索引.md").write_text(
                "# Root\n\n## 例外目录\n- `packaged-skill/` — 发布制品不嵌入记忆\n",
                encoding="utf-8",
            )
            excluded = root / "packaged-skill"
            excluded.mkdir()
            (excluded / "README.md").write_text("release package", encoding="utf-8")
            included = root / "real-module"
            included.mkdir()
            (included / "README.md").write_text("project module", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                memory_manager.cmd_check(SimpleNamespace(workspace=str(root), scope="", max_depth=0))
            text = output.getvalue()
            self.assertIn("real-module", text)
            self.assertNotIn("packaged-skill", text)

    def test_layer_scan_obeys_root_index_exception_paths(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            memory = root / "记忆第一层"
            memory.mkdir()
            (memory / "0_索引.md").write_text(
                "## 例外目录\n- `release-copy/` — packaged skill\n", encoding="utf-8"
            )
            hidden = root / "release-copy" / "记忆第一层"
            hidden.mkdir(parents=True)
            actual = list(memory_manager.iter_memory_layers(root))
            self.assertEqual(actual, [memory])

    def test_search_obeys_root_index_exception_paths(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            memory = root / "记忆第一层"
            memory.mkdir()
            (memory / "0_索引.md").write_text(
                "## 例外目录\n- `release-copy/` — packaged skill\n", encoding="utf-8"
            )
            visible = memory / "notes.md"
            visible.write_text("VISIBLE_TERM\n", encoding="utf-8")
            hidden = root / "release-copy" / "记忆第一层"
            hidden.mkdir(parents=True)
            (hidden / "notes.md").write_text("HIDDEN_TERM\n", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                memory_manager.cmd_search(SimpleNamespace(
                    workspace=str(root), keyword="HIDDEN_TERM", term=[], scope="", top=10
                ))
            self.assertNotIn("HIDDEN_TERM", output.getvalue())

    def test_explicit_search_scope_cannot_override_root_exceptions(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            memory = root / "记忆第一层"
            memory.mkdir()
            (memory / "0_索引.md").write_text(
                "## 例外目录\n- `release-copy/` — packaged skill\n", encoding="utf-8"
            )
            excluded = root / "release-copy" / "记忆第二层"
            excluded.mkdir(parents=True)
            (excluded / "notes.md").write_text("SECRET_TERM\n", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                memory_manager.cmd_search(SimpleNamespace(
                    workspace=str(root), keyword="SECRET_TERM", term=[],
                    scope="release-copy", top=10
                ))
            self.assertIn("例外目录", output.getvalue())
            self.assertNotIn("SECRET_TERM", output.getvalue())

    def test_explicit_integrity_scope_under_exception_is_skipped(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            memory = root / "记忆第一层"
            memory.mkdir()
            (memory / "0_索引.md").write_text(
                "## 例外目录\n- `release-copy/` — packaged skill\n", encoding="utf-8"
            )
            excluded = root / "release-copy"
            excluded.mkdir()
            (excluded / "README.md").write_text("package", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                memory_manager.cmd_check(SimpleNamespace(
                    workspace=str(root), scope="release-copy", max_depth=0
                ))
            self.assertIn("已跳过", output.getvalue())
            self.assertNotIn("候选目录", output.getvalue())

    def test_absolute_and_parent_traversal_exceptions_are_rejected(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            memory = root / "记忆第一层"
            memory.mkdir()
            (memory / "0_索引.md").write_text(
                "## 例外目录\n"
                "- `/outside/` — absolute\n"
                "- `C:\\private\\` — drive path\n"
                "- `../outside/` — traversal\n"
                "- `safe/child/` — relative\n",
                encoding="utf-8",
            )
            self.assertEqual(memory_manager.declared_exclusions(root), ["safe/child"])

    def test_integrity_audit_reports_unreadable_directories(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            blocked = root / "blocked"
            blocked.mkdir()
            original_iterdir = Path.iterdir

            def deny_blocked(path):
                if path == blocked:
                    raise PermissionError("simulated access denied")
                return original_iterdir(path)

            output = io.StringIO()
            with patch.object(Path, "iterdir", deny_blocked):
                with contextlib.redirect_stdout(output):
                    memory_manager.cmd_check(SimpleNamespace(
                        workspace=str(root), scope="", max_depth=0
                    ))
            self.assertIn("扫描结果不完整", output.getvalue())
            self.assertIn("simulated access denied", output.getvalue())

    def test_text_writer_preserves_utf8_and_lf(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "记忆.md"
            memory_manager.write_text(path, "第一行\n第二行\n")
            self.assertEqual(path.read_bytes(), "第一行\n第二行\n".encode("utf-8"))

    def test_index_clears_fingerprint_for_intentionally_deleted_optional_topic(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self._make_layer(root, "记忆第一层", "root")
            layer = root / "记忆第一层"
            optional = layer / "6_需要我配合.txt"
            optional.write_text("# Pending\n", encoding="utf-8")
            index_args = SimpleNamespace(workspace=str(root), layer_dir="记忆第一层", by="test")

            with contextlib.redirect_stdout(io.StringIO()):
                memory_manager.cmd_index(index_args)
            indexed = memory_manager.load_index(layer)
            indexed["files"]["custom-notes.md"] = {"sha256": "preserve-me"}
            memory_manager.save_index(layer, indexed)
            optional.unlink()

            verify_args = SimpleNamespace(
                workspace=str(root), layer_dir="记忆第一层", refresh=False, by="test"
            )
            warning = io.StringIO()
            with contextlib.redirect_stdout(warning):
                memory_manager.cmd_verify(verify_args)
            self.assertIn("已被删除：6_需要我配合.txt", warning.getvalue())

            refreshed = io.StringIO()
            with contextlib.redirect_stdout(refreshed):
                memory_manager.cmd_index(index_args)
            self.assertIn("已清除已删除标准记忆文件的旧指纹", refreshed.getvalue())

            clean = io.StringIO()
            with contextlib.redirect_stdout(clean):
                memory_manager.cmd_verify(verify_args)
            self.assertIn("自上次记录后无外部改动", clean.getvalue())
            self.assertNotIn("6_需要我配合.txt", memory_manager.load_index(layer)["files"])
            self.assertEqual(
                memory_manager.load_index(layer)["files"]["custom-notes.md"]["sha256"],
                "preserve-me",
            )

    def test_scope_outside_workspace_is_rejected(self):
        with TemporaryDirectory() as temp, TemporaryDirectory() as outside_temp:
            root = Path(temp)
            outside = Path(outside_temp)
            with self.assertRaises(SystemExit):
                memory_manager.resolve_scope(root, str(outside))

    def test_search_is_case_insensitive_scoped_and_limited(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            layer = root / "记忆第一层"
            layer.mkdir()
            (layer / "notes.md").write_text("Alpha rule\nBeta clue\nalpha second\n", encoding="utf-8")
            other = root / "other" / "记忆第一层"
            other.mkdir(parents=True)
            (other / "notes.md").write_text("alpha elsewhere\n", encoding="utf-8")
            args = SimpleNamespace(workspace=str(root), keyword="ALPHA", term=[], scope=str(layer), top=1)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                memory_manager.cmd_search(args)
            text = output.getvalue()
            self.assertIn("Alpha rule", text)
            self.assertNotIn("elsewhere", text)
            self.assertIn("返回 1 行", text)

    def _make_layer(self, parent, name, label):
        layer = parent / name
        layer.mkdir()
        (layer / "0_索引.md").write_text(f"# {label}\n", encoding="utf-8")
        (layer / "5_代办.md").write_text(f"# {label} status\n", encoding="utf-8")
        data = {"files": {}}
        for filename in ("0_索引.md", "5_代办.md"):
            path = layer / filename
            data["files"][filename] = memory_manager.fingerprint_of(path)
        data["_last_updated_by"] = "test"
        memory_manager.save_index(layer, data)


if __name__ == "__main__":
    unittest.main()
