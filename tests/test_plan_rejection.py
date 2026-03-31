"""Tests for plan_node rejection loop.

Ensures that if the user rejects a plan via WebUI MAX_ATTEMPTS times,
the node aborts the round by setting should_stop = True and returning the state.
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state import OptimizerState
from nodes.plan import plan_node
import ui.web_server as ws_mod


class FakeLLM:
    def generate_json(self, messages):
        return {
            "expected_diff": ["fake expected diff"],
            "target_files": ["src/main.py"],
            "acceptance_checks": ["ensure fake check passes"],
        }


def test_plan_node_aborts_after_max_rejections(tmp_path):
    """If wait_for_user_command continuously returns 'replan_plan',
    plan_node should eventually give up and set should_stop = True.
    """
    state = OptimizerState({
        "project_path": str(tmp_path),
        "optimization_goal": "test goal",
        "current_round": 1,
        "max_rounds": 1,
        "should_stop": False,
        "ui_preferences": {"skip_plan_review": False},
        "llm": FakeLLM(),
    })

    # write a dummy file
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main(): pass")

    # mock file_ops to return this file
    with patch("nodes.plan.get_project_files", return_value=["src/main.py"]):
        with patch.object(ws_mod, "_clients", [MagicMock()]):
            with patch.object(ws_mod, "wait_for_user_command", return_value={"action": "replan_plan", "note": "reject"}):
                with patch.object(ws_mod, "emit"):
                    # We expect plan_node to loop 5 times (MAX_ATTEMPTS) and then set should_stop = True.
                    updated_state = plan_node(state)

    assert updated_state["should_stop"] is True
    assert "aborted" in str(updated_state.get("code_diff", "")).lower()

