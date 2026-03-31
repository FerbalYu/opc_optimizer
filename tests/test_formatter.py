"""Tests for utils/formatter.py (v2.8.0)."""

import os
import sys
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.formatter import detect_formatter, parse_formatter_spec, format_file


class TestDetectFormatter:
    def test_no_project_files(self):
        """Empty dir → no formatter detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = detect_formatter(tmpdir)
            assert result is None

    def test_pyproject_ruff(self):
        """pyproject.toml with [tool.ruff] → ruff format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
                f.write("[tool.ruff]\nline-length = 88\n")
            with patch("shutil.which", side_effect=lambda x: x if x == "ruff" else None):
                result = detect_formatter(tmpdir)
                assert result is not None
                assert result["name"] == "ruff format"
                assert ".py" in result["extensions"]

    def test_pyproject_black(self):
        """pyproject.toml with [tool.black] → black."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
                f.write("[tool.black]\nline-length = 88\n")
            with patch("shutil.which", side_effect=lambda x: x if x == "black" else None):
                result = detect_formatter(tmpdir)
                assert result is not None
                assert result["name"] == "black"

    def test_pyproject_ruff_priority_over_black(self):
        """Ruff should be detected before black when both are present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
                f.write("[tool.ruff]\n[tool.black]\n")
            with patch("shutil.which", return_value="found"):
                result = detect_formatter(tmpdir)
                assert result is not None
                assert "ruff" in result["name"]

    def test_prettierrc(self):
        """Project with .prettierrc → prettier."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, ".prettierrc"), "w") as f:
                f.write("{}")
            with patch("shutil.which", side_effect=lambda x: x if x in ("npx", "prettier") else None):
                result = detect_formatter(tmpdir)
                assert result is not None
                assert "prettier" in result["name"]

    def test_package_json_prettier(self):
        """package.json with prettier dep → prettier."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "package.json"), "w") as f:
                json.dump({"devDependencies": {"prettier": "^3.0"}}, f)
            with patch("shutil.which", side_effect=lambda x: x if x == "npx" else None):
                result = detect_formatter(tmpdir)
                assert result is not None
                assert "prettier" in result["name"]

    def test_go_mod(self):
        """Project with go.mod → gofmt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "go.mod"), "w") as f:
                f.write("module example\n")
            with patch("shutil.which", side_effect=lambda x: x if x == "gofmt" else None):
                result = detect_formatter(tmpdir)
                assert result is not None
                assert result["name"] == "gofmt"

    def test_cargo_toml(self):
        """Project with Cargo.toml → rustfmt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "Cargo.toml"), "w") as f:
                f.write("[package]\nname = \"test\"\n")
            with patch("shutil.which", side_effect=lambda x: x if x == "rustfmt" else None):
                result = detect_formatter(tmpdir)
                assert result is not None
                assert result["name"] == "rustfmt"

    def test_formatter_not_installed(self):
        """Detected config but tool not in PATH → None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
                f.write("[tool.black]\n")
            with patch("shutil.which", return_value=None):
                result = detect_formatter(tmpdir)
                assert result is None


class TestParseFormatterSpec:
    def test_empty(self):
        assert parse_formatter_spec("") is None
        assert parse_formatter_spec("   ") is None

    def test_simple_name(self):
        result = parse_formatter_spec("black")
        assert result is not None
        assert result["command"] == ["black"]
        assert ".py" in result["extensions"]

    def test_with_flags(self):
        result = parse_formatter_spec("black --quiet --line-length 88")
        assert result is not None
        assert result["command"] == ["black", "--quiet", "--line-length", "88"]

    def test_ruff_format(self):
        result = parse_formatter_spec("ruff format")
        assert result is not None
        assert result["command"] == ["ruff", "format"]
        assert ".py" in result["extensions"]

    def test_unknown_tool(self):
        result = parse_formatter_spec("mytool --fancy")
        assert result is not None
        assert result["command"] == ["mytool", "--fancy"]
        assert result["extensions"] == []


class TestFormatFile:
    def test_no_formatter(self):
        ok, msg = format_file(None, "/tmp/test.py")
        assert not ok
        assert "No formatter" in msg

    def test_wrong_extension(self):
        fmt = {"name": "black", "command": ["black"], "extensions": [".py"]}
        ok, msg = format_file(fmt, "/tmp/test.js")
        assert ok  # Skipped is still "success"
        assert "Skipped" in msg

    def test_command_not_found(self):
        fmt = {"name": "nonexistent", "command": ["__nonexistent_formatter__"], "extensions": [".py"]}
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1\n")
            f.flush()
            ok, msg = format_file(fmt, f.name)
        os.unlink(f.name)
        assert not ok
        assert "not installed" in msg or "not found" in msg.lower()

    def test_format_real_file(self):
        """Test with a mock subprocess that succeeds."""
        fmt = {"name": "test-fmt", "command": ["echo"], "extensions": [".py"]}
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1\n")
            filepath = f.name

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            ok, msg = format_file(fmt, filepath)
        os.unlink(filepath)
        assert ok
        assert "Formatted" in msg
