"""Integration tests for skill chain execution."""

import pytest

from utils.skill_bridge import build_base_skill_plan, run_skill


def test_skill_chain_runs_end_to_end_with_contracts():
    call_order = []

    def plan_handler(state):
        call_order.append("plan")
        state["current_plan"] = "do changes"
        state["round_contract"] = {"target_files": ["main.py"]}
        return state

    def execute_handler(state):
        call_order.append("execute")
        state["code_diff"] = "MODIFIED main.py"
        state["modified_files"] = ["main.py"]
        return state

    def test_handler(state):
        call_order.append("test")
        state["test_results"] = "all passed"
        state["build_result"] = {"build_passed": True, "test_passed": True}
        state["round_evaluation"] = {"value_score": 8}
        return state

    def interact_handler(state):
        call_order.append("interact")
        state["should_stop"] = False
        state["current_round"] = state.get("current_round", 1) + 1
        return state

    def report_handler(state):
        call_order.append("report")
        state["round_reports"] = [{"round": 1, "status": "ok"}]
        state["round_history"] = [{"round": 1}]
        return state

    handlers = {
        "plan": plan_handler,
        "execute": execute_handler,
        "test": test_handler,
        "interact": interact_handler,
        "report": report_handler,
    }
    state = {
        "project_path": ".",
        "optimization_goal": "improve quality",
        "current_round": 1,
        "max_rounds": 3,
    }

    for skill in build_base_skill_plan():
        state = run_skill(skill, state, handlers=handlers)

    assert call_order == ["plan", "execute", "test", "interact", "report"]
    assert state["current_round"] == 2
    assert state["round_reports"][0]["status"] == "ok"


def test_skill_chain_breaks_when_contract_output_missing():
    def plan_handler(state):
        state["current_plan"] = "do changes"
        state["round_contract"] = {}
        return state

    def execute_handler_missing_output(state):
        state["code_diff"] = "MODIFIED main.py"
        # Missing `modified_files` should trigger output-contract error.
        return state

    handlers = {
        "plan": plan_handler,
        "execute": execute_handler_missing_output,
    }
    state = {
        "project_path": ".",
        "optimization_goal": "improve quality",
        "current_round": 1,
    }

    state = run_skill("plan", state, handlers=handlers)
    with pytest.raises(ValueError):
        run_skill("execute", state, handlers=handlers)

