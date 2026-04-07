"""Tests for scripts/evaluate_rollout.py."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.evaluate_rollout import evaluate_rollout


def _write_metrics(project_dir, rows):
    opclog = os.path.join(project_dir, ".opclog")
    os.makedirs(opclog, exist_ok=True)
    path = os.path.join(opclog, "metrics.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _row(mode, failure_type="none", build_passed=True, test_passed=True):
    return {
        "run_mode": mode,
        "failure_type": failure_type,
        "build_passed": build_passed,
        "test_passed": test_passed,
    }


def test_evaluate_rollout_insufficient_data(tmp_path):
    _write_metrics(str(tmp_path), [_row("legacy_mode"), _row("skill_mode")])
    result = evaluate_rollout(str(tmp_path), min_rounds=5)
    assert result["recommendation"] == "insufficient_data"


def test_evaluate_rollout_recommends_rollback_on_high_skill_failure(tmp_path):
    rows = [
        _row("legacy_mode", "none"),
        _row("legacy_mode", "none"),
        _row("skill_mode", "router_failed"),
        _row("skill_mode", "build_failed"),
        _row("skill_mode", "none"),
    ]
    _write_metrics(str(tmp_path), rows)
    result = evaluate_rollout(str(tmp_path), min_rounds=5, max_skill_failure_rate=0.2)
    assert result["recommendation"] == "rollback_skill"


def test_evaluate_rollout_can_promote_skill_default(tmp_path):
    rows = [
        _row("skill_mode", "none"),
        _row("skill_mode", "none"),
        _row("skill_mode", "none"),
        _row("legacy_mode", "none"),
        _row("legacy_mode", "none"),
        _row("skill_mode", "none"),
    ]
    _write_metrics(str(tmp_path), rows)
    result = evaluate_rollout(str(tmp_path), min_rounds=5, promote_min_skill_share=0.5)
    assert result["recommendation"] == "promote_skill_default"

