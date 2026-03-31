"""Integration tests for plan_node and test_node using MockLLMService."""

import os
import sys
import shutil
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
        "code_diff": "",
        "test_results": "",
        "should_stop": False,
        "round_reports": [],
        "execution_errors": [],
        "modified_files": [],
        "auto_mode": True,
        "dry_run": False,
        "archive_every_n_rounds": 3,
    }
    state.update(overrides)
    return state


class TestPlanNodeIntegration:
    @patch("nodes.plan.LLMService")
    def test_generates_plan_file(self, MockLLM, tmp_project):
        mock_instance = MockLLMService(json_response={
            "round_objective": "Fix bug in main.py",
            "current_state_assessment": "main.py contains a bug.",
            "target_files": ["main.py"],
            "acceptance_checks": ["main.py should contain the updated function body."],
            "expected_diff": ["Modify the buggy function in main.py."],
            "risk_level": "low",
            "fallback_if_blocked": "Restrict the change to the smallest safe fix.",
            "impact_score": 8,
            "confidence_score": 8,
            "verification_score": 7,
            "effort_score": 3,
        })
        MockLLM.return_value = mock_instance
        MockLLM.truncate_to_budget = staticmethod(lambda text, budget, label="": text)
        MockLLM.estimate_tokens = staticmethod(lambda text: len(text) // 4)

        from nodes.plan import plan_node
        state = _make_state(tmp_project)
        result = plan_node(state)

        assert result["current_plan"] != ""
        assert result["round_contract"]["target_files"] == ["main.py"]
        plan_path = os.path.join(str(tmp_project), ".opclog", "plan.md")
        contract_path = os.path.join(str(tmp_project), ".opclog", "round_contract.json")
        assert os.path.exists(plan_path)
        assert os.path.exists(contract_path)
        with open(plan_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "Round Contract" in content
        assert "Fix bug in main.py" in content

    @patch("nodes.plan.LLMService")
    def test_uses_previous_suggestions(self, MockLLM, tmp_project):
        mock_instance = MockLLMService(json_response={
            "round_objective": "Plan based on suggestions",
            "current_state_assessment": "Suggestions point to utils.py.",
            "target_files": ["utils.py"],
            "acceptance_checks": ["utils.py change should address the prior suggestion."],
            "expected_diff": ["Touch the typo or bug in utils.py."],
            "risk_level": "low",
            "fallback_if_blocked": "Limit the round to typo correction.",
            "impact_score": 6,
            "confidence_score": 7,
            "verification_score": 5,
            "effort_score": 2,
        })
        MockLLM.return_value = mock_instance
        MockLLM.truncate_to_budget = staticmethod(lambda text, budget, label="": text)
        MockLLM.estimate_tokens = staticmethod(lambda text: len(text) // 4)

        from nodes.plan import plan_node
        state = _make_state(tmp_project, suggestions="Fix the typo in utils.py")
        result = plan_node(state)
        
        # Verify LLM was called with suggestions context
        call = mock_instance.call_log[0]
        prompt = call["messages"][1]["content"]
        assert "Fix the typo in utils.py" in prompt

    @patch("nodes.plan.LLMService")
    def test_initial_round_scans_files(self, MockLLM, tmp_project):
        mock_instance = MockLLMService(json_response={
            "round_objective": "Initial plan",
            "current_state_assessment": "Initial scan of project files.",
            "target_files": ["main.py"],
            "acceptance_checks": ["Plan should focus on one file."],
            "expected_diff": ["One meaningful code change in main.py."],
            "risk_level": "medium",
            "fallback_if_blocked": "Do the smallest safe change in main.py.",
            "impact_score": 7,
            "confidence_score": 6,
            "verification_score": 5,
            "effort_score": 4,
        })
        MockLLM.return_value = mock_instance
        MockLLM.truncate_to_budget = staticmethod(lambda text, budget, label="": text)
        MockLLM.estimate_tokens = staticmethod(lambda text: len(text) // 4)

        from nodes.plan import plan_node
        state = _make_state(tmp_project, suggestions="")
        result = plan_node(state)
        
        call = mock_instance.call_log[0]
        prompt = call["messages"][1]["content"]
        assert "Initial" in prompt or "first" in prompt.lower()


class TestTestNodeIntegration:
    @patch("nodes.test.LLMService")
    @patch("nodes.test._detect_and_run_build")
    def test_generates_suggestions(self, mock_build, MockLLM, tmp_project):
        mock_build.return_value = "Detected Python project.\n[pytest] exit_code=0\nall tests passed"
        mock_instance = MockLLMService(text_response="# Suggestions\n- Improve error handling")
        MockLLM.return_value = mock_instance

        from nodes.test import test_node
        state = _make_state(tmp_project, code_diff="MODIFIED main.py: added type hints")
        result = test_node(state)

        assert result["suggestions"] != ""
        assert "Suggestions" in result["suggestions"]
        suggestions_path = os.path.join(str(tmp_project), ".opclog", "suggestions.md")
        assert os.path.exists(suggestions_path)

    @patch("nodes.test.LLMService")
    @patch("nodes.test._detect_and_run_build")
    def test_build_failure_increments_no_improvements(self, mock_build, MockLLM, tmp_project):
        mock_build.return_value = "[pytest] exit_code=1\nAssertionError: test failed"
        mock_instance = MockLLMService(text_response="Build failed, suggestions...")
        MockLLM.return_value = mock_instance

        from nodes.test import test_node
        state = _make_state(tmp_project, consecutive_no_improvements=0)
        result = test_node(state)
        assert result["consecutive_no_improvements"] == 1

    @patch("nodes.test.LLMService")
    @patch("nodes.test._detect_and_run_build")
    def test_build_success_resets_counter(self, mock_build, MockLLM, tmp_project):
        mock_build.return_value = "[pytest] exit_code=0\nall passed"
        mock_instance = MockLLMService(text_response="All good")
        MockLLM.return_value = mock_instance

        from nodes.test import test_node
        state = _make_state(tmp_project, consecutive_no_improvements=1)
        result = test_node(state)
        assert result["consecutive_no_improvements"] == 0

    @patch("nodes.test.LLMService")
    @patch("nodes.test._detect_and_run_build")
    def test_build_failure_triggers_rollback(self, mock_build, MockLLM, tmp_project):
        # Setup: create a .bak file to simulate pre-modification backup
        main_py = tmp_project / "main.py"
        original_content = main_py.read_text(encoding='utf-8')
        bak_path = tmp_project / "main.py.bak"
        shutil.copy2(str(main_py), str(bak_path))
        # "Modify" the file
        main_py.write_text("BROKEN CODE", encoding='utf-8')

        mock_build.return_value = "[pytest] exit_code=1\nSyntaxError"
        mock_instance = MockLLMService(text_response="Build failed")
        MockLLM.return_value = mock_instance

        from nodes.test import test_node
        state = _make_state(tmp_project, modified_files=["main.py"])
        result = test_node(state)

        # File should be rolled back
        restored = main_py.read_text(encoding='utf-8')
        assert restored == original_content
        assert result["modified_files"] == []


class TestLLMServiceTokenBudget:
    def test_truncate_to_budget_short_text(self):
        from utils.llm import LLMService
        text = "short text"
        result = LLMService.truncate_to_budget(text, 1000)
        assert result == text  # Should not truncate

    def test_truncate_to_budget_long_text(self):
        from utils.llm import LLMService
        text = "x" * 500_000  # Very long text
        result = LLMService.truncate_to_budget(text, 1000, label="test")
        assert len(result) < len(text)
        assert "TRUNCATED" in result

    def test_estimate_tokens_english(self):
        from utils.llm import LLMService
        # ~100 chars English → ~25 tokens
        text = "a" * 100
        tokens = LLMService.estimate_tokens(text)
        assert 20 <= tokens <= 30

    def test_estimate_tokens_cjk(self):
        from utils.llm import LLMService
        text = "你好世界" * 10  # 40 CJK chars → ~40 tokens
        tokens = LLMService.estimate_tokens(text)
        assert 35 <= tokens <= 45
