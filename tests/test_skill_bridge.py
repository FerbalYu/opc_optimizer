"""Tests for `utils.skill_bridge`."""

import pytest

from utils.skill_bridge import build_base_skill_plan, run_skill


def test_build_base_skill_plan_order():
    plan = build_base_skill_plan()
    assert plan == ["plan", "execute", "test", "interact", "report"]


def test_run_skill_delegates_to_handler_and_sets_skill_name():
    calls = []

    def fake_plan(state):
        calls.append(("plan", state.get("x")))
        state["y"] = "ok"
        state["current_plan"] = "step1"
        state["round_contract"] = {}
        return state

    state = {"x": 1, "project_path": ".", "optimization_goal": "goal", "current_round": 1}
    result = run_skill("plan", state, handlers={"plan": fake_plan})
    assert result["skill_name"] == "plan"
    assert result["y"] == "ok"
    assert calls == [("plan", 1)]


def test_run_skill_raises_for_unknown_skill():
    with pytest.raises(ValueError):
        run_skill("unknown", {}, handlers={})


def test_run_skill_raises_when_input_contract_missing():
    with pytest.raises(ValueError):
        run_skill("plan", {"project_path": "."}, handlers={"plan": lambda s: s})


def test_run_skill_raises_when_output_contract_missing():
    state = {"project_path": ".", "optimization_goal": "goal", "current_round": 1}
    with pytest.raises(ValueError):
        run_skill("plan", state, handlers={"plan": lambda s: s})


def test_run_skill_updates_original_state_reference():
    def fake_plan(state):
        state["current_plan"] = "ok"
        state["round_contract"] = {"a": 1}
        return state

    state = {"project_path": ".", "optimization_goal": "goal", "current_round": 1}
    result = run_skill("plan", state, handlers={"plan": fake_plan})
    assert result is state
    assert state["skill_name"] == "plan"
