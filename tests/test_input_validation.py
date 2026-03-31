"""Tests for input validation and sanitization."""

import pytest
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from nodes.interact import _sanitize_input, _validate_goal


class TestSanitizeInput:
    """Test _sanitize_input function."""

    def test_empty_string(self):
        """Empty input should return empty."""
        assert _sanitize_input("") == ""
        assert _sanitize_input(None) == ""

    def test_whitespace_trimmed(self):
        """Leading/trailing whitespace should be trimmed."""
        assert _sanitize_input("  hello  ") == "hello"

    def test_truncation(self):
        """Input exceeding max_length should be truncated."""
        long_text = "a" * 1000
        result = _sanitize_input(long_text, max_length=100)
        assert len(result) == 100


class TestValidateGoal:
    """Test _validate_goal function."""

    def test_normal_goal(self):
        """Normal goal should pass through unchanged."""
        goal = "Improve code quality and performance"
        assert _validate_goal(goal) == goal

    def test_empty_goal(self):
        """Empty goal should return empty."""
        assert _validate_goal("") == ""

    def test_dangerous_import_blocked(self):
        """__import__ should be sanitized."""
        goal = "Do something with __import__('os')"
        result = _validate_goal(goal)
        assert "__import__" not in result
        assert "***" in result

    def test_dangerous_eval_blocked(self):
        """eval() should be sanitized."""
        goal = "eval('os.system()')"
        result = _validate_goal(goal)
        assert "eval" not in result
        assert "***" in result

    def test_dangerous_exec_blocked(self):
        """exec() should be sanitized."""
        goal = "exec('os.system()')"
        result = _validate_goal(goal)
        assert "exec" not in result
        assert "***" in result

    def test_template_injection_blocked(self):
        """${...} template injection should be sanitized."""
        goal = "Use ${env:SECRET} in output"
        result = _validate_goal(goal)
        assert "${" not in result
        assert "***" in result

    def test_script_tag_blocked(self):
        """<script> tags should be sanitized."""
        goal = "Add <script>alert('xss')</script> to page"
        result = _validate_goal(goal)
        assert "<script>" not in result
        assert "***" in result

    def test_javascript_protocol_blocked(self):
        """javascript: URLs should be sanitized."""
        goal = "Link to javascript:alert(1)"
        result = _validate_goal(goal)
        assert "javascript:" not in result
        assert "***" in result

    def test_normal_length_goal(self):
        """Normal length goal should work fine."""
        goal = "Improve error handling and add more unit tests"
        assert _validate_goal(goal) == goal
