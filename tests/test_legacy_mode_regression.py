"""Regression tests to ensure legacy_mode behavior remains stable."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from graph import _build_skill_dispatcher


@pytest.mark.parametrize("skill_name", ["plan", "execute", "test", "report", "interact"])
def test_legacy_mode_uses_legacy_handler_for_all_core_skills(skill_name):
    calls = []

    def legacy_fn(state):
        calls.append(skill_name)
        state["legacy_result"] = f"{skill_name}:ok"
        return state

    dispatcher = _build_skill_dispatcher(skill_name, legacy_fn)
    state = {"run_mode": "legacy_mode", "failure_type": "none"}
    result = dispatcher(state)

    assert calls == [skill_name]
    assert result["legacy_result"] == f"{skill_name}:ok"
    assert result["skill_name"] == "legacy_pipeline"


def test_legacy_mode_is_unaffected_even_if_skill_runtime_is_broken(monkeypatch):
    def legacy_fn(state):
        state["legacy_ok"] = True
        return state

    def broken_run_skill(skill_name, state):
        raise RuntimeError("skill runtime broken")

    monkeypatch.setattr("utils.skill_bridge.run_skill", broken_run_skill, raising=True)

    dispatcher = _build_skill_dispatcher("plan", legacy_fn)
    result = dispatcher({"run_mode": "legacy_mode", "failure_type": "none"})

    assert result["legacy_ok"] is True
    assert result["run_mode"] == "legacy_mode"
    assert result.get("failure_type", "none") == "none"

