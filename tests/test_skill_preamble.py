"""Tests for `utils.skill_preamble`."""

from utils.skill_preamble import inject_skill_preamble


def test_inject_skill_preamble_sets_state_fields():
    state = {
        "current_round": 2,
        "run_mode": "skill_mode",
        "auto_mode": True,
        "dry_run": False,
        "ui_preferences": {"skip_plan_review": True},
        "llm_config": {"timeout": 180},
    }
    profile = {"type": "python", "languages": ["python"], "detected_by": "rules"}

    preamble = inject_skill_preamble(state, profile)

    assert state["session_id"].startswith("opc-")
    assert state["round_id"] == "round-2"
    assert state["skill_preamble"] == preamble
    assert state["preamble_context"]["project_profile"]["type"] == "python"
    assert "session_id" in preamble
    assert "round_id" in preamble
    assert "run_mode: skill_mode" in preamble


def test_inject_skill_preamble_keeps_existing_session_id():
    state = {
        "session_id": "opc-fixed-session",
        "current_round": 1,
        "run_mode": "legacy_mode",
        "llm_config": {},
    }
    preamble = inject_skill_preamble(state, {"type": "unknown", "languages": []})
    assert state["session_id"] == "opc-fixed-session"
    assert state["round_id"] == "round-1"
    assert "opc-fixed-session" in preamble


def test_inject_skill_preamble_uses_default_timeout_and_profile_values():
    state = {
        "current_round": 3,
        "run_mode": "legacy_mode",
        "ui_preferences": {},
        "llm_config": {},
    }
    preamble = inject_skill_preamble(state, {})
    assert state["preamble_context"]["config"]["timeout"] == 120
    assert state["preamble_context"]["project_profile"]["type"] == "unknown"
    assert "languages=unknown" in preamble
