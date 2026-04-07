"""Tests for scripts/decide_rollout_mode.py."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.decide_rollout_mode import build_rollout_decision, decide_rollout_mode


def test_build_decision_promote_default():
    decision = build_rollout_decision(
        {"recommendation": "promote_skill_default", "reason": "stable enough"}
    )
    assert decision["target_run_mode"] == "skill_mode"
    assert decision["target_gray_percent"] == 100
    assert decision["rollout_action"] == "promote_default"


def test_build_decision_rollback():
    decision = build_rollout_decision(
        {"recommendation": "rollback_skill", "reason": "too many failures"}
    )
    assert decision["target_run_mode"] == "legacy_mode"
    assert decision["target_gray_percent"] == 0
    assert decision["rollout_action"] == "rollback"


def test_decide_rollout_mode_writes_decision_file(tmp_path):
    opclog = tmp_path / ".opclog"
    opclog.mkdir(parents=True, exist_ok=True)
    (opclog / "rollout_evaluation.json").write_text(
        json.dumps({"recommendation": "insufficient_data", "reason": "not enough rounds"}),
        encoding="utf-8",
    )
    decision = decide_rollout_mode(str(tmp_path))
    assert decision["rollout_action"] == "collect_more_data"
    out_path = opclog / "rollout_decision.json"
    assert out_path.exists()

