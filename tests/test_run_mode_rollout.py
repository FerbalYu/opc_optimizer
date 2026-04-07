"""Tests for run mode gray rollout resolution in main.py."""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import _resolve_run_mode


def _args(**kwargs):
    base = {
        "run_mode": None,
        "skill_gray_percent": None,
        "project_path": "D:/demo/project",
        "goal": "improve quality",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_explicit_run_mode_has_highest_priority(monkeypatch):
    monkeypatch.setenv("OPC_RUN_MODE", "legacy_mode")
    monkeypatch.setenv("OPC_SKILL_GRAY_PERCENT", "100")
    assert _resolve_run_mode(_args(run_mode="skill_mode")) == "skill_mode"


def test_env_run_mode_overrides_gray_rollout(monkeypatch):
    monkeypatch.setenv("OPC_RUN_MODE", "legacy_mode")
    monkeypatch.setenv("OPC_SKILL_GRAY_PERCENT", "100")
    assert _resolve_run_mode(_args()) == "legacy_mode"


def test_gray_zero_is_legacy(monkeypatch):
    monkeypatch.delenv("OPC_RUN_MODE", raising=False)
    monkeypatch.setenv("OPC_SKILL_GRAY_PERCENT", "0")
    assert _resolve_run_mode(_args()) == "legacy_mode"


def test_gray_hundred_is_skill(monkeypatch):
    monkeypatch.delenv("OPC_RUN_MODE", raising=False)
    monkeypatch.setenv("OPC_SKILL_GRAY_PERCENT", "100")
    assert _resolve_run_mode(_args()) == "skill_mode"


def test_gray_rollout_is_deterministic_for_same_seed(monkeypatch):
    monkeypatch.delenv("OPC_RUN_MODE", raising=False)
    monkeypatch.delenv("OPC_SKILL_GRAY_PERCENT", raising=False)
    args = _args(skill_gray_percent=50, project_path="D:/same/path", goal="same-goal")
    first = _resolve_run_mode(args)
    second = _resolve_run_mode(args)
    assert first == second

