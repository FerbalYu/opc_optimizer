"""Tests for utils/config_template.py (v2.9.0)."""

import os
import sys
import json
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.config_template import (
    detect_project_type,
    validate_project_path,
    generate_template,
)


class TestDetectProjectType:
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = detect_project_type(tmpdir)
            assert result["valid"] is True
            assert result["file_count"] == 0
            assert result["types"] == []

    def test_nonexistent_dir(self):
        result = detect_project_type("/nonexistent_12345")
        assert result["valid"] is False

    def test_python_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create marker
            with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
                f.write("[project]\n")
            # Create .py files
            for i in range(3):
                with open(os.path.join(tmpdir, f"mod_{i}.py"), "w") as f:
                    f.write(f"x = {i}\n")
            result = detect_project_type(tmpdir)
            assert "python" in result["types"]
            assert result["primary"] == "python"
            assert result["details"]["python"]["files"] == 3
            assert result["details"]["python"]["icon"] == "🐍"

    def test_js_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "package.json"), "w") as f:
                json.dump({"name": "test"}, f)
            with open(os.path.join(tmpdir, "app.js"), "w") as f:
                f.write("console.log(1);\n")
            result = detect_project_type(tmpdir)
            assert "javascript" in result["types"]
            assert result["details"]["javascript"]["files"] == 1

    def test_go_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "go.mod"), "w") as f:
                f.write("module test\n")
            with open(os.path.join(tmpdir, "main.go"), "w") as f:
                f.write("package main\n")
            result = detect_project_type(tmpdir)
            assert "go" in result["types"]

    def test_mixed_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
                f.write("[project]\n")
            for i in range(5):
                with open(os.path.join(tmpdir, f"mod_{i}.py"), "w") as f:
                    f.write("pass\n")
            with open(os.path.join(tmpdir, "package.json"), "w") as f:
                json.dump({}, f)
            with open(os.path.join(tmpdir, "ui.js"), "w") as f:
                f.write("x()\n")
            result = detect_project_type(tmpdir)
            assert len(result["types"]) >= 2
            assert result["primary"] == "python"  # more .py files

    def test_skip_dirs(self):
        """node_modules and .git should be skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nm = os.path.join(tmpdir, "node_modules")
            os.makedirs(nm)
            with open(os.path.join(nm, "lib.js"), "w") as f:
                f.write("x\n")
            result = detect_project_type(tmpdir)
            assert result["file_count"] == 0


class TestValidateProjectPath:
    def test_empty(self):
        result = validate_project_path("")
        assert result["valid"] is False
        assert "路径不能为空" in result["message"]

    def test_nonexistent(self):
        result = validate_project_path("/nonexistent_path_abc")
        assert result["valid"] is False
        assert result["exists"] is False

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_project_path(tmpdir)
            assert result["valid"] is False
            assert "未检测到" in result["message"]

    def test_valid_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "main.py"), "w") as f:
                f.write("pass\n")
            result = validate_project_path(tmpdir)
            assert result["valid"] is True
            assert "✅" in result["message"]
            assert "1" in result["message"]


class TestGenerateTemplate:
    def test_basic(self):
        template = generate_template()
        assert "OPC Optimizer" in template
        assert "goal:" in template
        assert "max_rounds:" in template
        assert "formatter:" in template
        assert "timeout:" in template

    def test_with_python_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
                f.write("[project]\n")
            with open(os.path.join(tmpdir, "main.py"), "w") as f:
                f.write("pass\n")
            template = generate_template(tmpdir)
            assert "Python" in template

    def test_nonexistent_path(self):
        template = generate_template("/nonexistent_abc_123")
        # Should not crash, just skip project detection
        assert "goal:" in template

    def test_sections(self):
        template = generate_template()
        for section in ["基础配置", "运行模式", "LLM 配置", "格式化", "文件过滤", "安全"]:
            assert section in template
