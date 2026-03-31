"""End-to-end workflow tests for the OPC optimizer.

Tests the complete flow: plan -> execute using MockLLMService.
"""

import os
import sys
import pytest
from unittest.mock import patch

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
        "code_diff": "",
        "test_results": "",
        "should_stop": False,
        "round_reports": [],
        "execution_errors": [],
        "modified_files": [],
        "auto_mode": True,
        "dry_run": False,
        "archive_every_n_rounds": 3,
        "round_evaluation": {},
        "round_history": [],
        "build_result": {},
        "active_tasks": [],
        "node_timings": {},
    }
    state.update(overrides)
    return state


class TestPlanNodeWorkflow:
    """Test plan_node workflow."""

    @patch("nodes.plan.LLMService")
    def test_plan_generates_contract(self, MockLLM, tmp_project):
        """Test that plan_node generates a proper round contract."""
        mock_instance = MockLLMService(
            json_response={
                "round_objective": "Add docstrings to functions",
                "current_state_assessment": "Functions lack docstrings.",
                "target_files": ["main.py"],
                "acceptance_checks": ["main.py functions should have docstrings."],
                "expected_diff": ["Add docstring to hello() function."],
                "risk_level": "low",
                "fallback_if_blocked": "Add the simplest docstring.",
                "impact_score": 5,
                "confidence_score": 8,
                "verification_score": 7,
                "effort_score": 2,
            }
        )
        MockLLM.return_value = mock_instance
        MockLLM.truncate_to_budget = staticmethod(lambda text, budget, label="": text)
        MockLLM.estimate_tokens = staticmethod(lambda text: len(text) // 4)

        from nodes.plan import plan_node

        state = _make_state(tmp_project)
        result = plan_node(state)

        assert result["current_plan"] != ""
        assert "target_files" in result["round_contract"]
        assert result["round_contract"]["target_files"] == ["main.py"]

    @patch("nodes.plan.LLMService")
    def test_plan_uses_suggestions_context(self, MockLLM, tmp_project):
        """Test that plan_node uses previous suggestions as context."""
        mock_instance = MockLLMService(
            json_response={
                "round_objective": "Fix performance issue",
                "current_state_assessment": "Performance needs improvement.",
                "target_files": ["utils.py"],
                "acceptance_checks": ["utils.py should be faster."],
                "expected_diff": ["Optimize the add() function."],
                "risk_level": "medium",
                "fallback_if_blocked": "Make minimal optimization.",
                "impact_score": 7,
                "confidence_score": 6,
                "verification_score": 6,
                "effort_score": 4,
            }
        )
        MockLLM.return_value = mock_instance
        MockLLM.truncate_to_budget = staticmethod(lambda text, budget, label="": text)
        MockLLM.estimate_tokens = staticmethod(lambda text: len(text) // 4)

        from nodes.plan import plan_node

        state = _make_state(
            tmp_project, suggestions="Consider caching the add() result"
        )
        result = plan_node(state)

        assert result["current_plan"] != ""
        assert (
            "add" in result["current_plan"].lower()
            or "performance" in result["current_plan"].lower()
        )


class TestExecuteNodeWorkflow:
    """Test execute_node workflow."""

    @patch("nodes.execute.LLMService")
    def test_execute_applies_modifications(self, MockLLM, tmp_project):
        """Test that execute_node applies file modifications."""
        mock_instance = MockLLMService(
            json_response={
                "modifications": [
                    {
                        "filepath": "main.py",
                        "old_content_snippet": "def hello():",
                        "new_content": 'def hello():\n    """Say hello."""',
                        "description": "Add docstring to hello()",
                    }
                ]
            }
        )
        MockLLM.return_value = mock_instance
        MockLLM.truncate_to_budget = staticmethod(lambda text, budget, label="": text)
        MockLLM.estimate_tokens = staticmethod(lambda text: len(text) // 4)

        from nodes.execute import execute_node

        state = _make_state(
            tmp_project,
            round_contract={
                "target_files": ["main.py"],
                "acceptance_checks": ["main.py should have docstrings."],
            },
        )
        result = execute_node(state)

        assert "modified_files" in result

    @patch("nodes.execute.LLMService")
    def test_execute_respects_dry_run(self, MockLLM, tmp_project):
        """Test that execute_node doesn't modify files in dry_run mode."""
        mock_instance = MockLLMService(
            json_response={
                "modifications": [
                    {
                        "filepath": "main.py",
                        "old_content_snippet": "def hello():",
                        "new_content": "def greet():",
                        "description": "Rename function",
                    }
                ]
            }
        )
        MockLLM.return_value = mock_instance
        MockLLM.truncate_to_budget = staticmethod(lambda text, budget, label="": text)
        MockLLM.estimate_tokens = staticmethod(lambda text: len(text) // 4)

        from nodes.execute import execute_node

        original_content = (tmp_project / "main.py").read_text(encoding="utf-8")

        state = _make_state(
            tmp_project,
            dry_run=True,
            round_contract={
                "target_files": ["main.py"],
                "acceptance_checks": ["main.py should be modified."],
            },
        )
        result = execute_node(state)

        current_content = (tmp_project / "main.py").read_text(encoding="utf-8")
        assert current_content == original_content


class TestWorkflowIntegration:
    """Test plan -> execute workflow integration."""

    @patch("nodes.execute.LLMService")
    @patch("nodes.plan.LLMService")
    def test_plan_to_execute_flow(self, MockPlanLLM, MockExecLLM, tmp_project):
        """Test that plan output flows correctly into execute input."""
        plan_response = {
            "round_objective": "Add type hints",
            "current_state_assessment": "Code needs type hints.",
            "target_files": ["utils.py"],
            "acceptance_checks": ["utils.py should have type hints."],
            "expected_diff": ["Add type hints to add()"],
            "risk_level": "low",
            "fallback_if_blocked": "Add minimal type hint.",
            "impact_score": 6,
            "confidence_score": 7,
            "verification_score": 6,
            "effort_score": 3,
        }
        exec_response = {
            "modifications": [
                {
                    "filepath": "utils.py",
                    "old_content_snippet": "def add(a, b):",
                    "new_content": "def add(a: int, b: int) -> int:",
                    "description": "Add type hints",
                }
            ]
        }

        mock_plan = MockLLMService(json_response=plan_response)
        MockPlanLLM.return_value = mock_plan
        MockPlanLLM.truncate_to_budget = staticmethod(
            lambda text, budget, label="": text
        )
        MockPlanLLM.estimate_tokens = staticmethod(lambda text: len(text) // 4)

        mock_exec = MockLLMService(json_response=exec_response)
        MockExecLLM.return_value = mock_exec
        MockExecLLM.truncate_to_budget = staticmethod(
            lambda text, budget, label="": text
        )
        MockExecLLM.estimate_tokens = staticmethod(lambda text: len(text) // 4)

        from nodes.plan import plan_node
        from nodes.execute import execute_node

        state = _make_state(tmp_project)

        plan_result = plan_node(state)
        assert plan_result["round_contract"]["target_files"] == ["utils.py"]

        exec_result = execute_node(plan_result)
        assert "modified_files" in exec_result
