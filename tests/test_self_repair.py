"""Tests for crash self-repair and complexity penalty in test.py — autoresearch-inspired features."""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nodes.test import _apply_self_repair_patches, _evaluate_round_outcome, test_node as run_test_node


def _make_state(tmp_project, **overrides):
    state = {
        "project_path": str(tmp_project),
        "optimization_goal": "Improve code quality",
        "current_round": 1,
        "max_rounds": 5,
        "consecutive_no_improvements": 0,
        "suggestions": "",
        "current_plan": "",
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
        "archive_every_n_rounds": 3,
    }
    state.update(overrides)
    return state


class TestComplexityPenalty:
    def test_large_diff_low_value_gets_penalty(self, tmp_project):
        """A large diff (>100 lines) with low value score should be penalized."""
        # Build a code_diff with 120+ lines
        big_diff = "\n".join(f"MODIFIED line {i}" for i in range(120))
        state = _make_state(
            tmp_project,
            round_contract={
                "target_files": ["main.py", "utils.py"],
                "acceptance_checks": [],
                "expected_diff": ["In utils.py: Add validation"],  # doesn't match main.py
                "impact_score": 3,
                "confidence_score": 3,
                "verification_score": 3,
            },
            modified_files=["main.py"],
            code_diff=big_diff,
        )

        result = _evaluate_round_outcome(state, build_passed=True)

        assert "change_magnitude" in result
        assert result["change_magnitude"]["diff_lines"] >= 120
        # Should have a complexity penalty reason
        has_penalty = any("Complexity penalty" in r for r in result["reasons"])
        assert has_penalty, f"Expected complexity penalty, got reasons: {result['reasons']}"

    def test_large_diff_high_value_no_penalty(self, tmp_project):
        """A large diff with high value score should NOT be penalized."""
        big_diff = "\n".join(f"MODIFIED line {i}" for i in range(120))
        state = _make_state(
            tmp_project,
            round_contract={
                "target_files": ["main.py"],
                "acceptance_checks": ["main.py should be improved", "Performance boost"],
                "expected_diff": ["In main.py: Major refactoring"],
                "impact_score": 9,
                "confidence_score": 9,
                "verification_score": 9,
            },
            modified_files=["main.py"],
            code_diff=big_diff,
        )

        result = _evaluate_round_outcome(state, build_passed=True)

        has_complexity_penalty = any("Complexity penalty" in r for r in result["reasons"])
        # value_score should be high enough (>= 6) to avoid penalty
        assert not has_complexity_penalty, \
            f"Should not have complexity penalty for high-value round, value={result['value_score']}, reasons: {result['reasons']}"

    def test_many_files_low_value_gets_scope_penalty(self, tmp_project):
        """Changing >5 files with low value should trigger a scope penalty."""
        many_files = ["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"]
        state = _make_state(
            tmp_project,
            round_contract={
                "target_files": many_files,  # all in scope to avoid out-of-scope preempting
                "acceptance_checks": [],
                "expected_diff": ["In z.py: Something else"],  # non-matching to keep value low
                "impact_score": 3,
                "confidence_score": 3,
                "verification_score": 3,
            },
            modified_files=many_files,
            code_diff="MODIFIED a.py\nMODIFIED b.py\nMODIFIED c.py\nMODIFIED d.py\nMODIFIED e.py\nMODIFIED f.py",
        )

        result = _evaluate_round_outcome(state, build_passed=True)

        has_scope = any("Scope penalty" in r for r in result["reasons"])
        assert has_scope, f"Expected scope penalty, got value_score={result['value_score']}, reasons: {result['reasons']}"

    def test_small_diff_no_penalty(self, tmp_project):
        """A small diff should never trigger complexity penalty."""
        state = _make_state(
            tmp_project,
            round_contract={
                "target_files": ["main.py"],
                "acceptance_checks": [],
                "expected_diff": ["In main.py: Fix typo"],
                "impact_score": 3,
                "confidence_score": 3,
                "verification_score": 3,
            },
            modified_files=["main.py"],
            code_diff="MODIFIED main.py: Fix typo",
        )

        result = _evaluate_round_outcome(state, build_passed=True)

        has_complexity = any("Complexity penalty" in r for r in result["reasons"])
        assert not has_complexity

    def test_change_magnitude_in_result(self, tmp_project):
        """The change_magnitude field should always be present."""
        state = _make_state(
            tmp_project,
            modified_files=["main.py"],
            code_diff="MODIFIED main.py: one line change",
        )

        result = _evaluate_round_outcome(state, build_passed=True)

        assert "change_magnitude" in result
        assert "diff_lines" in result["change_magnitude"]
        assert "files_count" in result["change_magnitude"]
        assert result["change_magnitude"]["files_count"] == 1


class TestSelfRepairPatches:
    def test_applies_search_replace_patch_from_diff_parser_shape(self, tmp_project):
        main_py = tmp_project / "main.py"
        main_py.write_text("def hello():\n    return 'broken'\n", encoding="utf-8")

        applied = _apply_self_repair_patches(
            str(tmp_project),
            [
                {
                    "filepath": "<main.py>",
                    "old_content_snippet": "    return 'broken'",
                    "new_content": "    return 'fixed'",
                }
            ],
            ["main.py"],
        )

        assert applied == 1
        assert "return 'fixed'" in main_py.read_text(encoding="utf-8")

    def test_rejects_patch_outside_modified_files(self, tmp_project):
        (tmp_project / "other.py").write_text("value = 'broken'\n", encoding="utf-8")

        applied = _apply_self_repair_patches(
            str(tmp_project),
            [
                {
                    "filepath": "other.py",
                    "old_content_snippet": "broken",
                    "new_content": "fixed",
                }
            ],
            ["main.py"],
        )

        assert applied == 0
        assert "broken" in (tmp_project / "other.py").read_text(encoding="utf-8")

    def test_test_node_self_repair_rechecks_after_applying_patch(self, tmp_project, monkeypatch):
        monkeypatch.setenv("OPC_MAX_SELF_REPAIR", "1")
        main_py = tmp_project / "main.py"
        main_py.write_text("def hello():\n    return 'broken'\n", encoding="utf-8")

        class FakeRepairLLM:
            def generate(self, _messages):
                return "\n".join([
                    "FILE: main.py",
                    "<<<<<<< SEARCH",
                    "    return 'broken'",
                    "=======",
                    "    return 'fixed'",
                    ">>>>>>> REPLACE",
                ])

        class FakeReviewLLM:
            def generate(self, _messages):
                return "修复已通过真实测试。"

        state = _make_state(
            tmp_project,
            modified_files=["main.py"],
            code_diff="MODIFIED main.py",
            round_contract={
                "target_files": ["main.py"],
                "acceptance_checks": ["python -m pytest -q passes"],
                "expected_diff": ["main.py returns fixed"],
            },
        )

        with patch(
            "utils.project_profile.load_project_profile",
            return_value={
                "type": "python",
                "build_cmd": "python -m py_compile main.py",
                "test_cmd": "python -m pytest -q",
            },
        ), patch(
            "nodes.test._detect_and_run_build",
            return_value="[build] exit_code=0\nok",
        ), patch(
            "nodes.test._run_build_check",
            return_value={"passed": True, "output": "[build] exit_code=0\nok", "skipped": False},
        ) as rerun_build, patch(
            "nodes.test._run_test_check",
            side_effect=[
                {"passed": False, "output": "[test] exit_code=1\nAssertionError", "skipped": False},
                {"passed": True, "output": "[test] exit_code=0\n1 passed", "skipped": False},
            ],
        ) as run_test, patch(
            "nodes.test._run_ui_check",
            return_value={"passed": True, "output": "UI verification disabled - skipped.", "skipped": True},
        ), patch(
            "nodes.test._get_llm",
            side_effect=[FakeRepairLLM(), FakeReviewLLM()],
        ):
            result = run_test_node(state)

        assert "return 'fixed'" in main_py.read_text(encoding="utf-8")
        assert result["build_result"]["build_passed"] is True
        assert result["build_result"]["test_passed"] is True
        assert result["build_result"]["validation_mode"] == "real"
        assert rerun_build.called
        assert run_test.call_count == 2
