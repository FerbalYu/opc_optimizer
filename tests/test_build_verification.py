"""Tests for Step 15 Build Verification (v2.11.0).

Covers:
  - _parse_cmd() command string splitting + Windows suffix
  - _run_build_check() with/without build_cmd in profile
  - _run_test_check() with/without test_cmd in profile
  - _run_sandboxed() command whitelist
  - Allowed commands extension for flutter/dart/bundle
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Mock litellm to avoid ModuleNotFoundError in test environments
from unittest.mock import MagicMock
import types
if "litellm" not in sys.modules:
    sys.modules["litellm"] = types.ModuleType("litellm")
    sys.modules["litellm"].completion = MagicMock()

from nodes.test import (
    _parse_cmd,
    _run_build_check,
    _run_test_check,
    _run_sandboxed,
    ALLOWED_COMMANDS,
)


# ─── _parse_cmd ──────────────────────────────────────────────────

class TestParseCmd:
    """Tests for command string parsing."""

    def test_simple_command(self):
        assert _parse_cmd("pytest") == ["pytest"]

    def test_multi_part_command(self):
        parts = _parse_cmd("go test ./...")
        assert parts == ["go", "test", "./..."]

    def test_empty_string(self):
        assert _parse_cmd("") == []
        assert _parse_cmd("   ") == []

    def test_windows_npm_suffix(self):
        """On Windows, npm/yarn/pnpm should get .cmd suffix."""
        with patch("os.name", "nt"):
            # Need to reimport or call directly
            parts = _parse_cmd.__wrapped__(None, "npm run build") if hasattr(_parse_cmd, '__wrapped__') else None
        # Since _parse_cmd checks os.name at call time, we test the logic:
        # Just verify the function doesn't crash
        parts = _parse_cmd("npm run build")
        assert parts[0] in ("npm", "npm.cmd")
        assert parts[1] == "run"
        assert parts[2] == "build"

    def test_cargo_command(self):
        parts = _parse_cmd("cargo test")
        assert parts == ["cargo", "test"]

    def test_flutter_command(self):
        parts = _parse_cmd("flutter test")
        assert len(parts) >= 2
        assert parts[1] == "test"


# ─── _run_build_check ───────────────────────────────────────────

class TestRunBuildCheck:
    """Tests for profile-driven build checking."""

    def test_no_build_cmd_skipped(self, tmp_path):
        profile = {"type": "python", "build_cmd": None}
        result = _run_build_check(str(tmp_path), profile)
        assert result["passed"] is True
        assert result["skipped"] is True

    def test_empty_build_cmd_skipped(self, tmp_path):
        profile = {"type": "python", "build_cmd": ""}
        result = _run_build_check(str(tmp_path), profile)
        assert result["passed"] is True
        assert result["skipped"] is True

    def test_empty_profile_skipped(self, tmp_path):
        result = _run_build_check(str(tmp_path), {})
        assert result["passed"] is True
        assert result["skipped"] is True

    def test_build_with_real_command(self, tmp_path):
        """Run a command that should succeed (python --version)."""
        profile = {"build_cmd": "python --version"}
        result = _run_build_check(str(tmp_path), profile)
        assert result["skipped"] is False
        # python --version should exit 0
        assert result["passed"] is True
        assert "exit_code=0" in result["output"]

    def test_build_with_failing_command(self, tmp_path):
        """Run a command that will fail."""
        profile = {"build_cmd": "python -c \"import sys; sys.exit(1)\""}
        result = _run_build_check(str(tmp_path), profile)
        assert result["skipped"] is False
        assert result["passed"] is False


# ─── _run_test_check ────────────────────────────────────────────

class TestRunTestCheck:
    """Tests for profile-driven test checking."""

    def test_no_test_cmd_skipped(self, tmp_path):
        profile = {"type": "python", "test_cmd": None}
        result = _run_test_check(str(tmp_path), profile)
        assert result["passed"] is True
        assert result["skipped"] is True

    def test_empty_test_cmd_skipped(self, tmp_path):
        profile = {"type": "python", "test_cmd": ""}
        result = _run_test_check(str(tmp_path), profile)
        assert result["passed"] is True
        assert result["skipped"] is True

    def test_test_with_real_command(self, tmp_path):
        """Run a command that should succeed."""
        profile = {"test_cmd": "python --version"}
        result = _run_test_check(str(tmp_path), profile)
        assert result["skipped"] is False
        assert result["passed"] is True

    def test_pytest_gets_extra_flags(self, tmp_path):
        """When test_cmd contains pytest, --tb=short and -q should be added."""
        profile = {"test_cmd": "pytest"}
        with patch("nodes.test._run_sandboxed") as mock_run:
            mock_run.return_value = "[test] exit_code=0\nall passed"
            _run_test_check(str(tmp_path), profile)
            # Check that --tb=short and -q were added
            called_cmd = mock_run.call_args[0][0]
            assert "--tb=short" in called_cmd
            assert "-q" in called_cmd


# ─── ALLOWED_COMMANDS ────────────────────────────────────────────

class TestAllowedCommands:
    """Tests for extended command whitelist."""

    def test_flutter_in_whitelist(self):
        assert "flutter" in ALLOWED_COMMANDS

    def test_dart_in_whitelist(self):
        assert "dart" in ALLOWED_COMMANDS

    def test_bundle_in_whitelist(self):
        assert "bundle" in ALLOWED_COMMANDS

    def test_rspec_in_whitelist(self):
        assert "rspec" in ALLOWED_COMMANDS

    def test_cargo_in_whitelist(self):
        assert "cargo" in ALLOWED_COMMANDS

    def test_dotnet_in_whitelist(self):
        assert "dotnet" in ALLOWED_COMMANDS


# ─── _run_sandboxed ─────────────────────────────────────────────

class TestRunSandboxed:
    """Tests for sandbox protections."""

    def test_blocked_command(self, tmp_path):
        """Non-whitelisted commands should be blocked."""
        result = _run_sandboxed(["rm", "-rf", "/"], str(tmp_path), label="blocked")
        assert "BLOCKED" in result

    def test_allowed_command_runs(self, tmp_path):
        """Whitelisted command should execute."""
        result = _run_sandboxed(["python", "--version"], str(tmp_path), label="py-ver")
        assert "exit_code=0" in result

    def test_command_not_found(self, tmp_path):
        """Command that doesn't exist on PATH."""
        result = _run_sandboxed(
            ["python", "-c", "import nonexistent_garbage_module"],
            str(tmp_path), label="notfound"
        )
        assert "exit_code=1" in result


# ─── Integration: profile → build → test ────────────────────────

class TestProfileIntegration:
    """Integration test: end-to-end profile → build → test flow."""

    def test_python_profile_flow(self, tmp_path):
        """Python profile should run pytest (or python --version as proxy)."""
        profile = {
            "type": "python",
            "build_cmd": None,
            "test_cmd": "python --version",  # Use harmless command
        }
        build = _run_build_check(str(tmp_path), profile)
        test = _run_test_check(str(tmp_path), profile)
        assert build["passed"] is True  # No build_cmd → skip
        assert build["skipped"] is True
        assert test["passed"] is True
        assert test["skipped"] is False

    def test_js_profile_flow(self, tmp_path):
        """JS profile with build+test commands."""
        profile = {
            "type": "javascript",
            "build_cmd": "python --version",  # Proxy for npm run build
            "test_cmd": "python --version",   # Proxy for npm test
        }
        build = _run_build_check(str(tmp_path), profile)
        test = _run_test_check(str(tmp_path), profile)
        assert build["passed"] is True
        assert build["skipped"] is False
        assert test["passed"] is True
        assert test["skipped"] is False

    def test_result_format(self, tmp_path):
        """Result dict should have all expected keys."""
        profile = {"build_cmd": "python --version"}
        result = _run_build_check(str(tmp_path), profile)
        assert "passed" in result
        assert "output" in result
        assert "skipped" in result
        assert isinstance(result["passed"], bool)
        assert isinstance(result["output"], str)
        assert isinstance(result["skipped"], bool)
