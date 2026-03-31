"""Tests for utils/project_profile.py (v2.10.0 — Step 14).

Covers:
  - Rule-table detection for various project types
  - LLM fallback (mocked)
  - Cache read/write/invalidation
  - Integration with file_ops.get_project_files()
"""

import os
import sys
import json
import tempfile
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.project_profile import (
    detect_project_profile,
    load_project_profile,
    invalidate_profile_cache,
    _compute_root_hash,
    _generate_dir_tree,
    _collect_clue_files,
    _match_rules,
    _generic_profile,
)
from utils.file_ops import get_project_files


# ─── Rule-table Detection ───────────────────────────────────────

class TestDetectProjectProfile:
    """Tests for detect_project_profile() rule-table matching."""

    def test_detect_python_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (open(os.path.join(tmpdir, "pyproject.toml"), "w")).close()
            (open(os.path.join(tmpdir, "main.py"), "w")).close()
            profile = detect_project_profile(tmpdir)
            assert profile["type"] == "python"
            assert ".py" in profile["scan_extensions"]
            assert ".pyi" in profile["scan_extensions"]
            assert profile["test_cmd"] == "pytest"
            assert profile["detected_by"] == "rules"

    def test_detect_js_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "package.json"), "w") as f:
                json.dump({"name": "test", "dependencies": {"express": "1.0"}}, f)
            profile = detect_project_profile(tmpdir)
            assert profile["type"] == "javascript"
            assert ".js" in profile["scan_extensions"]
            assert profile["build_cmd"] == "npm run build"
            assert profile["dev_cmd"] == "npm run dev"

    def test_detect_go_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "go.mod"), "w") as f:
                f.write("module test\n")
            profile = detect_project_profile(tmpdir)
            assert profile["type"] == "go"
            assert ".go" in profile["scan_extensions"]
            assert profile["test_cmd"] == "go test ./..."

    def test_detect_flutter_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "pubspec.yaml"), "w") as f:
                f.write("name: test_app\n")
            profile = detect_project_profile(tmpdir)
            assert profile["type"] == "flutter"
            assert ".dart" in profile["scan_extensions"]
            assert profile["dev_cmd"] == "flutter run -d chrome"

    def test_detect_wechat_miniprogram(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "app.json"), "w") as f:
                json.dump({"pages": ["pages/index/index"]}, f)
            with open(os.path.join(tmpdir, "app.wxss"), "w") as f:
                f.write("page { background: #fff; }")
            profile = detect_project_profile(tmpdir)
            assert profile["type"] == "微信小程序"
            assert ".wxml" in profile["scan_extensions"]
            assert ".wxss" in profile["scan_extensions"]
            assert any("setData" in h for h in profile["optimization_hints"])

    def test_detect_vue_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "package.json"), "w") as f:
                json.dump({"name": "vue-app", "dependencies": {"vue": "^3.0"}}, f)
            with open(os.path.join(tmpdir, "vite.config.ts"), "w") as f:
                f.write("export default {}\n")
            profile = detect_project_profile(tmpdir)
            assert profile["type"] == "vue"
            assert ".vue" in profile["scan_extensions"]
            assert profile["dev_cmd"] == "npm run dev"
            assert any("computed" in h for h in profile["optimization_hints"])

    def test_detect_react_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "package.json"), "w") as f:
                json.dump({"name": "react-app", "dependencies": {"react": "^18"}}, f)
            profile = detect_project_profile(tmpdir)
            assert profile["type"] == "react"
            assert profile["dev_cmd"] == "npm run dev"
            assert ".jsx" in profile["scan_extensions"] or ".tsx" in profile["scan_extensions"]

    def test_detect_rust_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "Cargo.toml"), "w") as f:
                f.write("[package]\nname = \"test\"\n")
            profile = detect_project_profile(tmpdir)
            assert profile["type"] == "rust"
            assert profile["build_cmd"] == "cargo build"

    def test_detect_nonexistent_returns_generic(self):
        profile = detect_project_profile("/nonexistent_path_12345")
        assert profile["type"] == "unknown"
        assert profile["detected_by"] == "fallback"

    def test_detect_empty_dir_no_llm(self):
        """Empty dir with no LLM should return fallback profile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = detect_project_profile(tmpdir)
            assert profile["type"] == "unknown"
            assert profile["detected_by"] == "fallback"


class TestDetectLLMFallback:
    """Tests for LLM fallback detection (mocked)."""

    def test_llm_fallback_called_when_no_rule_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files with unusual extensions
            with open(os.path.join(tmpdir, "main.zig"), "w") as f:
                f.write("const std = @import(\"std\");\n")

            mock_llm = MagicMock()
            mock_llm.generate_json.return_value = {
                "type": "zig",
                "languages": ["zig"],
                "scan_extensions": [".zig"],
                "test_cmd": "zig test",
                "build_cmd": "zig build",
                "dev_cmd": None,
                "formatter": None,
                "ignore_dirs": ["zig-cache", "zig-out"],
                "optimization_hints": ["使用 comptime 做编译期优化"],
            }

            profile = detect_project_profile(tmpdir, llm=mock_llm)
            assert profile["type"] == "zig"
            assert profile["detected_by"] == "llm"
            mock_llm.generate_json.assert_called_once()

    def test_llm_fallback_error_returns_generic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_llm = MagicMock()
            mock_llm.generate_json.side_effect = RuntimeError("API error")

            profile = detect_project_profile(tmpdir, llm=mock_llm)
            assert profile["type"] == "unknown"
            assert profile["detected_by"] == "fallback"


# ─── Profile Output Format ──────────────────────────────────────

class TestProfileFormat:
    """Tests for profile output format consistency."""

    def test_all_required_fields_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "go.mod"), "w") as f:
                f.write("module test\n")
            profile = detect_project_profile(tmpdir)
            required_fields = [
                "type", "languages", "scan_extensions", "test_cmd",
                "build_cmd", "dev_cmd", "formatter", "ignore_dirs", "optimization_hints",
                "detected_by",
            ]
            for field in required_fields:
                assert field in profile, f"Missing field: {field}"

    def test_generic_profile_format(self):
        profile = _generic_profile()
        assert isinstance(profile["scan_extensions"], list)
        assert isinstance(profile["optimization_hints"], list)
        assert profile["type"] == "unknown"

    def test_optimization_hints_are_nonempty_for_known_types(self):
        """Known project types should always have at least 1 optimization hint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
                f.write("[project]\n")
            profile = detect_project_profile(tmpdir)
            assert len(profile["optimization_hints"]) >= 1


# ─── Cache ───────────────────────────────────────────────────────

class TestProfileCache:
    """Tests for load_project_profile() caching logic."""

    def test_cache_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".opclog"), exist_ok=True)
            with open(os.path.join(tmpdir, "main.py"), "w") as f:
                f.write("pass\n")
            with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
                f.write("[project]\n")
            profile = load_project_profile(tmpdir)
            cache_path = os.path.join(tmpdir, ".opclog", ".project_profile.json")
            assert os.path.isfile(cache_path)
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            assert cached["type"] == "python"

    def test_cache_hit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".opclog"), exist_ok=True)
            with open(os.path.join(tmpdir, "main.py"), "w") as f:
                f.write("pass\n")
            with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
                f.write("[project]\n")

            # First call: detect + write cache
            p1 = load_project_profile(tmpdir)
            assert p1["type"] == "python"

            # Second call: should read from cache (no LLM needed)
            p2 = load_project_profile(tmpdir)
            assert p2["type"] == "python"
            assert p2.get("_root_hash") == p1.get("_root_hash")

    def test_cache_invalidation_on_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".opclog"), exist_ok=True)
            with open(os.path.join(tmpdir, "main.py"), "w") as f:
                f.write("pass\n")
            with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
                f.write("[project]\n")

            p1 = load_project_profile(tmpdir)
            old_hash = p1["_root_hash"]

            # Add a new file to root → hash changes
            with open(os.path.join(tmpdir, "go.mod"), "w") as f:
                f.write("module test\n")

            p2 = load_project_profile(tmpdir)
            # Because root listing changed, profile should be re-detected
            assert p2["_root_hash"] != old_hash

    def test_invalidate_cache_manual(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".opclog"), exist_ok=True)
            with open(os.path.join(tmpdir, "main.py"), "w") as f:
                f.write("pass\n")

            load_project_profile(tmpdir)
            cache_path = os.path.join(tmpdir, ".opclog", ".project_profile.json")
            assert os.path.isfile(cache_path)

            result = invalidate_profile_cache(tmpdir)
            assert result is True
            assert not os.path.isfile(cache_path)

    def test_invalidate_cache_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = invalidate_profile_cache(tmpdir)
            assert result is False


# ─── Helper Functions ────────────────────────────────────────────

class TestHelpers:
    """Tests for internal helper functions."""

    def test_compute_root_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "a.txt"), "w") as f:
                f.write("a")
            h1 = _compute_root_hash(tmpdir)
            assert isinstance(h1, str)
            assert len(h1) == 32  # md5 hex

            # Adding a file changes the hash
            with open(os.path.join(tmpdir, "b.txt"), "w") as f:
                f.write("b")
            h2 = _compute_root_hash(tmpdir)
            assert h1 != h2

    def test_generate_dir_tree(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "main.py"), "w") as f:
                f.write("pass\n")
            os.makedirs(os.path.join(tmpdir, "src"))
            with open(os.path.join(tmpdir, "src", "app.py"), "w") as f:
                f.write("pass\n")
            tree = _generate_dir_tree(tmpdir)
            assert "main.py" in tree
            assert "src/" in tree

    def test_generate_dir_tree_skips_git(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".git"))
            with open(os.path.join(tmpdir, ".git", "HEAD"), "w") as f:
                f.write("ref: refs/heads/main\n")
            tree = _generate_dir_tree(tmpdir)
            assert ".git" not in tree

    def test_collect_clue_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "README.md"), "w") as f:
                f.write("# My Project\nThis is a test.\n")
            clues = _collect_clue_files(tmpdir)
            assert "README.md" in clues
            assert "My Project" in clues


# ─── Integration with file_ops ──────────────────────────────────

class TestFileOpsIntegration:
    """Tests for the profile parameter in get_project_files()."""

    def test_profile_extensions_used(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "main.py"), "w") as f:
                f.write("pass\n")
            with open(os.path.join(tmpdir, "style.wxss"), "w") as f:
                f.write("page {}\n")
            with open(os.path.join(tmpdir, "page.wxml"), "w") as f:
                f.write("<view />\n")

            # Without profile: .wxss and .wxml should NOT be found
            files_no_profile = get_project_files(tmpdir)
            basenames_no = {os.path.basename(f) for f in files_no_profile}
            assert "style.wxss" not in basenames_no
            assert "page.wxml" not in basenames_no

            # With profile: .wxss and .wxml SHOULD be found
            profile = {"scan_extensions": [".wxss", ".wxml", ".py"]}
            files_with_profile = get_project_files(tmpdir, profile=profile)
            basenames_with = {os.path.basename(f) for f in files_with_profile}
            assert "style.wxss" in basenames_with
            assert "page.wxml" in basenames_with
            assert "main.py" in basenames_with

    def test_profile_ignore_dirs_merged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_dir = os.path.join(tmpdir, "miniprogram_npm")
            os.makedirs(custom_dir)
            with open(os.path.join(custom_dir, "lib.js"), "w") as f:
                f.write("module.exports = {}\n")
            with open(os.path.join(tmpdir, "app.js"), "w") as f:
                f.write("App({})\n")

            # Without profile: miniprogram_npm IS scanned
            files_no = get_project_files(tmpdir, extensions=[".js"])
            basenames_no = {os.path.basename(f) for f in files_no}
            assert "lib.js" in basenames_no

            # With profile: miniprogram_npm is IGNORED
            profile = {"ignore_dirs": ["miniprogram_npm"]}
            files_with = get_project_files(tmpdir, extensions=[".js"], profile=profile)
            basenames_with = {os.path.basename(f) for f in files_with}
            assert "lib.js" not in basenames_with
            assert "app.js" in basenames_with

    def test_backward_compat_no_profile(self):
        """Calling without profile should behave identically to before."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "main.py"), "w") as f:
                f.write("pass\n")
            with open(os.path.join(tmpdir, "app.js"), "w") as f:
                f.write("x()\n")
            files = get_project_files(tmpdir)
            basenames = {os.path.basename(f) for f in files}
            assert "main.py" in basenames
            assert "app.js" in basenames
