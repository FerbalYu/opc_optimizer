"""Tests for Step 18 Playwright UI verification."""

import os
import sys
import shutil
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

if "litellm" not in sys.modules:
    import types

    sys.modules["litellm"] = types.ModuleType("litellm")
    sys.modules["litellm"].completion = MagicMock()

from nodes.test import _default_dev_urls, _run_ui_check, test_node as optimizer_test_node


TEST_TMP_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", ".tmp", "playwright_tests")
)


@contextmanager
def managed_tmpdir(name: str):
    path = os.path.join(TEST_TMP_ROOT, name)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class TestDefaultDevUrls:
    def test_vue_prefers_vite_and_vue_ports(self):
        urls = _default_dev_urls({"type": "vue"})
        assert urls[0].endswith(":5173")
        assert any(url.endswith(":8080") for url in urls)

    def test_react_prefers_cra_port(self):
        urls = _default_dev_urls({"type": "react"})
        assert urls[0].endswith(":3000")


class TestRunUiCheck:
    def test_skips_when_disabled(self):
        with patch.dict(os.environ, {}, clear=False):
            result = _run_ui_check(".", {"type": "vue", "dev_cmd": "npm run dev"})
        assert result["passed"] is True
        assert result["skipped"] is True

    def test_skips_non_frontend_profiles(self):
        with patch.dict(os.environ, {"OPC_ENABLE_UI_CHECK": "true"}, clear=False):
            result = _run_ui_check(".", {"type": "python", "dev_cmd": None})
        assert result["passed"] is True
        assert result["skipped"] is True

    def test_times_out_when_server_never_starts(self):
        fake_proc = MagicMock()
        with patch.dict(os.environ, {"OPC_ENABLE_UI_CHECK": "true"}, clear=False), \
             patch("nodes.test._start_dev_server", return_value=fake_proc), \
             patch("nodes.test._wait_for_dev_server", return_value=None), \
             patch("nodes.test._terminate_process") as mock_terminate:
            result = _run_ui_check(".", {"type": "vue", "dev_cmd": "npm run dev"}, timeout=1)
        assert result["passed"] is False
        assert result["skipped"] is False
        mock_terminate.assert_called_once_with(fake_proc)

    def test_successful_ui_check(self):
        fake_proc = MagicMock()
        with managed_tmpdir("ui_check_success") as tmpdir, \
             patch.dict(os.environ, {"OPC_ENABLE_UI_CHECK": "true"}, clear=False), \
             patch("nodes.test._start_dev_server", return_value=fake_proc), \
             patch("nodes.test._wait_for_dev_server", return_value="http://127.0.0.1:5173"), \
             patch(
                 "nodes.test._capture_ui_with_playwright",
                 return_value={
                     "passed": True,
                     "output": "UI verification passed",
                     "screenshot": os.path.join(tmpdir, ".opclog", "ui_checks", "round_1.png"),
                 },
             ), \
             patch("nodes.test._terminate_process") as mock_terminate:
            os.makedirs(os.path.join(tmpdir, ".opclog"), exist_ok=True)
            result = _run_ui_check(tmpdir, {"type": "vue", "dev_cmd": "npm run dev"}, round_num=1)
        assert result["passed"] is True
        assert result["skipped"] is False
        assert result["url"] == "http://127.0.0.1:5173"
        mock_terminate.assert_called_once_with(fake_proc)


class TestTestNodeUiIntegration:
    def _make_state(self, project_path):
        return {
            "project_path": project_path,
            "optimization_goal": "Improve code quality",
            "current_round": 2,
            "max_rounds": 5,
            "consecutive_no_improvements": 0,
            "suggestions": "",
            "current_plan": "",
            "code_diff": "MODIFIED src/App.vue: modernize state logic",
            "test_results": "",
            "build_result": {},
            "should_stop": False,
            "round_reports": [],
            "execution_errors": [],
            "modified_files": [],
            "auto_mode": True,
            "dry_run": False,
            "archive_every_n_rounds": 3,
            "llm_config": {},
        }

    def test_test_node_records_ui_result(self):
        with managed_tmpdir("test_node_records_ui_result") as tmpdir, \
             patch("utils.project_profile.load_project_profile", return_value={"type": "vue", "dev_cmd": "npm run dev"}), \
             patch("nodes.test._run_build_check", return_value={"passed": True, "output": "[build] ok", "skipped": False}), \
             patch("nodes.test._run_test_check", return_value={"passed": True, "output": "[test] ok", "skipped": False}), \
             patch(
                 "nodes.test._run_ui_check",
                 return_value={
                     "passed": True,
                     "output": "[ui] ok",
                     "skipped": False,
                     "screenshot": os.path.join(tmpdir, ".opclog", "ui_checks", "round_2.png"),
                     "url": "http://127.0.0.1:5173",
                 },
             ), \
             patch("nodes.test._get_llm") as mock_get_llm:
            mock_get_llm.return_value.generate.return_value = "next suggestions"
            os.makedirs(os.path.join(tmpdir, ".opclog"), exist_ok=True)
            result = optimizer_test_node(self._make_state(tmpdir))

        assert result["build_result"]["ui_passed"] is True
        assert result["build_result"]["ui_skipped"] is False
        assert result["build_result"]["ui_url"] == "http://127.0.0.1:5173"
        assert "[ui] ok" in result["test_results"]

    def test_test_node_ui_failure_increments_counter(self):
        with managed_tmpdir("test_node_ui_failure_increments_counter") as tmpdir, \
             patch("utils.project_profile.load_project_profile", return_value={"type": "vue", "dev_cmd": "npm run dev"}), \
             patch("nodes.test._run_build_check", return_value={"passed": True, "output": "[build] ok", "skipped": False}), \
             patch("nodes.test._run_test_check", return_value={"passed": True, "output": "[test] ok", "skipped": False}), \
             patch("nodes.test._run_ui_check", return_value={"passed": False, "output": "[ui] failed", "skipped": False}), \
             patch("nodes.test._get_llm") as mock_get_llm:
            mock_get_llm.return_value.generate.return_value = "next suggestions"
            os.makedirs(os.path.join(tmpdir, ".opclog"), exist_ok=True)
            result = optimizer_test_node(self._make_state(tmpdir))

        assert result["consecutive_no_improvements"] == 1
        assert result["build_result"]["ui_passed"] is False
