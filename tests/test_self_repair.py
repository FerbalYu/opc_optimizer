"""Tests for crash self-repair and complexity penalty in test.py — autoresearch-inspired features."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nodes.test import _evaluate_round_outcome


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
