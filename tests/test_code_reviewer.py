import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.code_reviewer import CodeReviewer
from nodes.execute import _apply_modification


class TestCodeReviewer:
    """Tests for the CodeReviewer security scanner."""

    def setup_method(self):
        self.reviewer = CodeReviewer()

    # ── Block patterns ──

    def test_blocks_eval(self):
        is_safe, issues = self.reviewer.review("result = eval(user_input)")
        assert not is_safe
        assert any("eval()" in i for i in issues)

    def test_blocks_exec(self):
        is_safe, issues = self.reviewer.review("exec(some_code)")
        assert not is_safe
        assert any("exec()" in i for i in issues)

    def test_blocks_os_system(self):
        is_safe, issues = self.reviewer.review('os.system("rm -rf /")')
        assert not is_safe
        assert any("os.system()" in i for i in issues)

    def test_blocks_os_popen(self):
        is_safe, issues = self.reviewer.review('os.popen("cat /etc/passwd")')
        assert not is_safe

    def test_blocks_subprocess_shell_true(self):
        is_safe, issues = self.reviewer.review('subprocess.run("ls", shell=True)')
        assert not is_safe
        assert any("shell=True" in i for i in issues)

    def test_blocks_shutil_rmtree(self):
        is_safe, issues = self.reviewer.review('shutil.rmtree("/important")')
        assert not is_safe

    def test_blocks_dunder_import(self):
        is_safe, issues = self.reviewer.review('__import__("os").system("hack")')
        assert not is_safe

    def test_blocks_child_process(self):
        is_safe, issues = self.reviewer.review('const cp = require("child_process")')
        assert not is_safe

    # ── Warn patterns ──

    def test_warns_os_remove(self):
        is_safe, issues = self.reviewer.review('os.remove("temp.txt")')
        assert is_safe  # warn, not block
        assert len(issues) > 0
        assert any("WARNING" in i for i in issues)

    def test_warns_network_access(self):
        is_safe, issues = self.reviewer.review('requests.get("http://evil.com")')
        assert is_safe  # warn, not block
        assert len(issues) > 0

    def test_warns_environ_modification(self):
        is_safe, issues = self.reviewer.review('os.environ["PATH"] = "/tmp"')
        assert is_safe
        assert len(issues) > 0

    # ── Safe patterns ──

    def test_safe_pure_code(self):
        is_safe, issues = self.reviewer.review("def add(a, b):\n    return a + b\n")
        assert is_safe
        assert len(issues) == 0

    def test_safe_class_definition(self):
        code = """
class Calculator:
    def __init__(self):
        self.result = 0
    def add(self, x):
        self.result += x
        return self
"""
        is_safe, issues = self.reviewer.review(code)
        assert is_safe
        assert len(issues) == 0

    def test_safe_logging_code(self):
        code = 'logger.info("Processing file")\nprint("hello")\n'
        is_safe, issues = self.reviewer.review(code)
        assert is_safe
        assert len(issues) == 0

    # ── Multiple patterns ──

    def test_multiple_violations(self):
        code = 'eval(x)\nos.system("cmd")\nshutil.rmtree("/")'
        is_safe, issues = self.reviewer.review(code)
        assert not is_safe
        assert len(issues) >= 3


class TestCodeReviewIntegration:
    """Test that CodeReviewer is integrated into _apply_modification."""

    def test_blocks_malicious_modification(self, tmp_project):
        mod = {
            "filepath": "main.py",
            "old_content_snippet": "def hello():",
            "new_content": 'def hello():\n    eval("malicious_code")',
            "reason": "optimization"
        }
        result = _apply_modification(str(tmp_project), mod)
        assert result.startswith("BLOCKED")
        assert "code review rejected" in result
        # File should NOT be changed
        with open(tmp_project / "main.py", 'r', encoding='utf-8') as f:
            assert "eval" not in f.read()

    def test_allows_safe_modification(self, tmp_project):
        mod = {
            "filepath": "main.py",
            "old_content_snippet": "def hello():",
            "new_content": "def greet():",
            "reason": "better naming"
        }
        result = _apply_modification(str(tmp_project), mod)
        assert result.startswith("MODIFIED")
        with open(tmp_project / "main.py", 'r', encoding='utf-8') as f:
            assert "def greet():" in f.read()
