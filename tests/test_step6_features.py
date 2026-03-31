"""Tests for Step 6 (v2.2.0) features: multi-round memory, file ranking,
test generation plugin, and interactive Web UI commands.
"""

import os
import sys
import threading
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.mock_llm import MockLLMService


def _make_state(tmp_project, **overrides):
    """Build a minimal OptimizerState dict for testing."""
    state = {
        "project_path": str(tmp_project),
        "optimization_goal": "Improve code quality",
        "current_round": 1,
        "max_rounds": 5,
        "consecutive_no_improvements": 0,
        "suggestions": "",
        "current_plan": "",
        "round_contract": {},
        "code_diff": "MODIFIED main.py: added type hints",
        "test_results": "",
        "should_stop": False,
        "round_reports": [],
        "execution_errors": [],
        "modified_files": ["main.py"],
        "auto_mode": True,
        "dry_run": False,
        "archive_every_n_rounds": 3,
        "round_history": [],
        "node_timings": {},
    }
    state.update(overrides)
    return state


# ─── 6.1 Multi-round Memory ─────────────────────────────────────────

class TestRoundHistory:
    @patch("utils.git_ops.git_auto_commit")
    @patch("utils.checkpoint.save_checkpoint")
    def test_report_node_appends_round_history(self, mock_cp, mock_git, tmp_project):
        """report_node should append a summary dict to state['round_history']."""
        from nodes.report import report_node
        state = _make_state(tmp_project, current_round=2)
        result = report_node(state)

        history = result.get("round_history", [])
        assert len(history) == 1
        assert history[0]["round"] == 2
        assert "main.py" in history[0]["files_changed"]

    @patch("utils.git_ops.git_auto_commit")
    @patch("utils.checkpoint.save_checkpoint")
    def test_report_node_accumulates_history(self, mock_cp, mock_git, tmp_project):
        """Running report_node twice should accumulate two entries."""
        from nodes.report import report_node
        state = _make_state(tmp_project, current_round=1)
        result = report_node(state)
        result["current_round"] = 2
        result = report_node(result)
        assert len(result["round_history"]) == 2

    @patch("nodes.plan.LLMService")
    def test_plan_node_includes_history_in_prompt(self, MockLLM, tmp_project):
        """plan_node should inject round_history into the LLM prompt."""
        mock_instance = MockLLMService(json_response={
            "round_objective": "Plan v2",
            "current_state_assessment": "Use round history to avoid repeats.",
            "target_files": ["main.py"],
            "acceptance_checks": ["Do not repeat old edits."],
            "expected_diff": ["Touch main.py for a new change only."],
            "risk_level": "medium",
            "fallback_if_blocked": "Pick a different hotspot file.",
            "impact_score": 6,
            "confidence_score": 6,
            "verification_score": 5,
            "effort_score": 3,
        })
        MockLLM.return_value = mock_instance
        MockLLM.truncate_to_budget = staticmethod(lambda text, budget, label="": text)
        MockLLM.estimate_tokens = staticmethod(lambda text: len(text) // 4)

        from nodes.plan import plan_node

        history = [
            {"round": 1, "summary": "Fixed imports", "files_changed": ["main.py"], "suggestions": ""},
            {"round": 2, "summary": "Added tests", "files_changed": ["test_main.py"], "suggestions": ""},
        ]
        state = _make_state(
            tmp_project,
            round_history=history,
            suggestions="Do more",
            current_round=3,
        )
        plan_node(state)

        prompt = mock_instance.call_log[0]["messages"][1]["content"]
        assert "Round 1" in prompt
        assert "Round 2" in prompt
        assert "DO NOT repeat" in prompt

    @patch("nodes.plan.LLMService")
    def test_plan_node_works_without_history(self, MockLLM, tmp_project):
        """plan_node should work fine when round_history is empty."""
        mock_instance = MockLLMService(json_response={
            "round_objective": "Initial plan",
            "current_state_assessment": "No prior history exists.",
            "target_files": ["main.py"],
            "acceptance_checks": ["A contract should still be generated."],
            "expected_diff": ["A focused change in main.py."],
            "risk_level": "medium",
            "fallback_if_blocked": "Keep the change minimal.",
            "impact_score": 5,
            "confidence_score": 5,
            "verification_score": 4,
            "effort_score": 3,
        })
        MockLLM.return_value = mock_instance
        MockLLM.truncate_to_budget = staticmethod(lambda text, budget, label="": text)
        MockLLM.estimate_tokens = staticmethod(lambda text: len(text) // 4)

        from nodes.plan import plan_node
        state = _make_state(tmp_project, round_history=[], suggestions="")
        result = plan_node(state)
        assert result["current_plan"] != ""


# ─── 6.2 File Complexity Ranking ────────────────────────────────────

class TestFileComplexityRanking:
    def test_rank_files_by_complexity(self, tmp_path):
        from utils.file_ops import rank_files_by_complexity

        simple = tmp_path / "simple.py"
        simple.write_text("x = 1\ny = 2\n", encoding="utf-8")

        complex_f = tmp_path / "complex.py"
        complex_f.write_text(
            "class Foo:\n" + "".join(f"    def method_{i}(self):\n        pass\n" for i in range(20)),
            encoding="utf-8",
        )

        result = rank_files_by_complexity([str(simple), str(complex_f)])
        assert os.path.basename(result[0]) == "complex.py"

    def test_rank_files_skips_config(self, tmp_path):
        from utils.file_ops import rank_files_by_complexity

        init = tmp_path / "__init__.py"
        init.write_text("# big init\n" * 100, encoding="utf-8")

        regular = tmp_path / "views.py"
        regular.write_text("def view():\n    return 'ok'\n", encoding="utf-8")

        result = rank_files_by_complexity([str(init), str(regular)])
        assert os.path.basename(result[0]) == "views.py"
        assert os.path.basename(result[-1]) == "__init__.py"

    def test_rank_empty_list(self):
        from utils.file_ops import rank_files_by_complexity
        assert rank_files_by_complexity([]) == []


# ─── 6.3 Test Gen Plugin ────────────────────────────────────────────

class TestTestGenPlugin:
    def test_plugin_loads(self, tmp_path):
        import shutil
        from plugins import load_plugins

        plugin_src = os.path.join(os.path.dirname(__file__), "..", "plugins", "test_gen_plugin.py")
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        shutil.copy2(plugin_src, str(plugin_dir / "test_gen_plugin.py"))

        plugins = load_plugins(str(plugin_dir))
        names = [p.name for p in plugins]
        assert "test_gen" in names

    def test_plugin_no_modified_files(self, tmp_project):
        from plugins.test_gen_plugin import TestGenNode
        node = TestGenNode()
        state = _make_state(tmp_project, modified_files=[])
        result = node.run(state)
        assert "No files to generate tests for" in result.get("test_gen_results", "")


# ─── 6.4 Interactive Mode ───────────────────────────────────────────

class TestInteractiveMode:
    def test_web_ui_continue(self, tmp_project):
        """_try_web_ui_interact should handle 'continue' command."""
        from nodes.interact import _try_web_ui_interact

        state = _make_state(tmp_project, auto_mode=False, current_round=2)

        with patch("ui.web_server._clients", [MagicMock()]), \
             patch("ui.web_server.wait_for_user_command", return_value={"action": "continue"}), \
             patch("ui.web_server.emit"):
            handled = _try_web_ui_interact(state)

        assert handled is True
        assert state["should_stop"] is False
        assert state["current_round"] == 3

    def test_web_ui_stop(self, tmp_project):
        from nodes.interact import _try_web_ui_interact

        state = _make_state(tmp_project, auto_mode=False, current_round=2)

        with patch("ui.web_server._clients", [MagicMock()]), \
             patch("ui.web_server.wait_for_user_command", return_value={"action": "stop"}), \
             patch("ui.web_server.emit"):
            handled = _try_web_ui_interact(state)

        assert handled is True
        assert state["should_stop"] is True

    def test_web_ui_adjust_goal(self, tmp_project):
        from nodes.interact import _try_web_ui_interact

        state = _make_state(tmp_project, auto_mode=False, current_round=2)

        with patch("ui.web_server._clients", [MagicMock()]), \
             patch("ui.web_server.wait_for_user_command", return_value={"action": "adjust_goal", "goal": "Security"}), \
             patch("ui.web_server.emit"):
            handled = _try_web_ui_interact(state)

        assert handled is True
        assert state["optimization_goal"] == "Security"

    def test_fallback_when_no_clients(self, tmp_project):
        from nodes.interact import _try_web_ui_interact

        state = _make_state(tmp_project, auto_mode=False)

        with patch("ui.web_server._clients", []):
            handled = _try_web_ui_interact(state)

        assert handled is False

    def test_user_command_event(self):
        """wait_for_user_command should return when the event is set."""
        import ui.web_server as ws

        ws._user_command = None
        ws._user_command_event.clear()

        def simulate_command():
            import time
            time.sleep(0.1)
            ws._user_command = {"action": "continue"}
            ws._user_command_event.set()

        t = threading.Thread(target=simulate_command, daemon=True)
        t.start()

        result = ws.wait_for_user_command(timeout=2)
        assert result is not None
        assert result["action"] == "continue"
