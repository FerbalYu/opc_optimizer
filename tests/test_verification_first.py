"""Tests for Verification-First Mode for High-Risk Logic (Step 24)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nodes.plan import _normalize_round_contract, _render_round_contract
from nodes.execute import execute_node


def _make_state(tmp_project, **overrides):
    state = {
        "project_path": str(tmp_project),
        "optimization_goal": "Optimize core algorithm",
        "current_round": 1,
        "max_rounds": 5,
        "consecutive_no_improvements": 0,
        "suggestions": "",
        "current_plan": "We need to rewrite the core algorithm.",
        "round_contract": {},
        "round_evaluation": {},
        "code_diff": "",
        "test_results": "",
        "build_result": {},
        "should_stop": False,
        "round_reports": [],
        "execution_errors": [],
        "modified_files": [],
        "auto_mode": True,
        "dry_run": False,
    }
    state.update(overrides)
    return state


class DummyLLM:
    """A dummy LLM that records the prompt used."""
    def __init__(self, **kwargs):
        self.max_context_tokens = 16000
        self.last_prompt = ""

    def generate(self, messages):
        self.last_prompt = str(messages)
        # Return a dummy SEARCH/REPLACE block so it parses successfully
        return "FILE: dummy.py\n<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE"


class TestVerificationFirstPlan:
    def test_normalize_extracts_verification_first_mode(self):
        """Test _normalize_round_contract extracts verification_first_mode."""
        raw = {
            "round_objective": "test",
            "target_files": ["foo.py"],
            "verification_first_mode": True
        }
        contract = _normalize_round_contract(raw, ["foo.py"], "goal")
        assert contract["verification_first_mode"] is True

    def test_normalize_defaults_to_false(self):
        """Test _normalize_round_contract defaults to False."""
        raw = {
            "round_objective": "test",
            "target_files": ["foo.py"]
        }
        contract = _normalize_round_contract(raw, ["foo.py"], "goal")
        assert contract["verification_first_mode"] is False

    def test_render_includes_verification_first_mode(self):
        """Test _render_round_contract includes the flag."""
        contract = {
            "round_objective": "test",
            "verification_first_mode": True
        }
        rendered = _render_round_contract(contract, 1)
        assert "Verification-First Mode: True" in rendered


class TestVerificationFirstExecute:
    def test_execute_injects_prompt_when_mode_is_true(self, monkeypatch, tmp_project):
        """When verification_first_mode is True, the prompt contains the strict constraint."""
        dummy_llm = DummyLLM()
        monkeypatch.setattr("nodes.execute._get_llm", lambda *a, **k: dummy_llm)
        
        # We need a file in the project so the executor parsing doesn't fail entirely
        (tmp_project / "dummy.py").write_text("foo\n", encoding="utf-8")
        
        state = _make_state(
            tmp_project,
            round_contract={
                "target_files": ["dummy.py"],
                "verification_first_mode": True
            }
        )
        execute_node(state)
        
        # Check that the strict constraint was injected into the prompt
        assert "VERIFICATION-FIRST MODE ENFORCED" in dummy_llm.last_prompt
        assert "DO NOT modify the core business logic yet" in dummy_llm.last_prompt

    def test_execute_does_not_inject_when_mode_is_false(self, monkeypatch, tmp_project):
        """When verification_first_mode is False (or absent), the prompt lacks the constraint."""
        dummy_llm = DummyLLM()
        monkeypatch.setattr("nodes.execute._get_llm", lambda *a, **k: dummy_llm)
        
        (tmp_project / "dummy.py").write_text("foo\n", encoding="utf-8")
        
        state = _make_state(
            tmp_project,
            round_contract={
                "target_files": ["dummy.py"],
                "verification_first_mode": False
            }
        )
        execute_node(state)
        
        assert "VERIFICATION-FIRST MODE ENFORCED" not in dummy_llm.last_prompt
