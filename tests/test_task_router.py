"""Tests for `nodes.task_router` fallback behavior."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nodes.task_router as task_router_mod


def _make_state(**kwargs):
    state = {
        "optimization_goal": "optimize architecture",
        "current_round": 1,
        "llm_config": {},
        "run_mode": "skill_mode",
        "failure_type": "none",
    }
    state.update(kwargs)
    return state


def test_task_router_uses_skill_router_in_skill_mode():
    state = _make_state(optimization_goal="optimize architecture")
    result = task_router_mod.task_router_node(state)
    assert result["run_mode"] in ("skill_mode", "legacy_mode")
    assert "router" in result["router_decision"]


def test_task_router_fallback_to_legacy_on_router_failure():
    state = _make_state(llm_config={"force_router_error": True})
    result = task_router_mod.task_router_node(state)
    assert result["run_mode"] == "legacy_mode"
    assert result["skill_name"] == "legacy_pipeline"
    assert result["failure_type"] == "router_failed"
    assert "fallback_legacy" in result["router_decision"]

