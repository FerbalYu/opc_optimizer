"""Tests for round timeout guard in graph.py — autoresearch-inspired timeout enforcement."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from graph import safe_node_wrapper


def _make_state(tmp_path, **overrides):
    state = {
        "project_path": str(tmp_path),
        "optimization_goal": "Improve quality",
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
        "node_timings": {},
        "round_start_time": 0,
        "round_timeout": 0,
    }
    state.update(overrides)
    return state


def _passthrough_node(state):
    """A trivial node that just returns the state."""
    return dict(state)


class TestRoundTimeout:
    def test_no_timeout_when_disabled(self, tmp_project):
        """round_timeout=0 should never trigger timeout."""
        state = _make_state(
            tmp_project,
            round_timeout=0,
            round_start_time=time.time() - 9999,  # very old start
        )
        wrapped = safe_node_wrapper("test_node", _passthrough_node)
        result = wrapped(state)
        # Should complete without error
        assert "test_node" in (result.get("node_timings", {}) or {})

    def test_no_timeout_when_within_limit(self, tmp_project):
        """Should not timeout when elapsed < round_timeout."""
        state = _make_state(
            tmp_project,
            round_timeout=600,
            round_start_time=time.time(),  # just started
        )
        wrapped = safe_node_wrapper("test_node", _passthrough_node)
        result = wrapped(state)
        assert "test_node" in (result.get("node_timings", {}) or {})

    def test_timeout_triggers_when_exceeded(self, tmp_project):
        """Should trigger timeout when elapsed > round_timeout."""
        state = _make_state(
            tmp_project,
            round_timeout=1,  # 1 second limit
            round_start_time=time.time() - 100,  # started 100 seconds ago
        )
        wrapped = safe_node_wrapper("test_node", _passthrough_node)
        result = wrapped(state)
        # Timeout is caught by the except block in safe_node_wrapper
        # and recorded as an execution error
        errors = result.get("execution_errors", [])
        assert any("timeout" in str(e).lower() for e in errors), \
            f"Expected timeout error in execution_errors, got: {errors}"

    def test_no_timeout_without_start_time(self, tmp_project):
        """Should not timeout if round_start_time is 0 (not set)."""
        state = _make_state(
            tmp_project,
            round_timeout=1,
            round_start_time=0,
        )
        wrapped = safe_node_wrapper("test_node", _passthrough_node)
        result = wrapped(state)
        assert "test_node" in (result.get("node_timings", {}) or {})
