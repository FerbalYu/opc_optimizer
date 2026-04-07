"""Build rollout mode decision and rollback plan from evaluation results."""

import argparse
import json
import os
from typing import Dict, Any


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_rollout_evaluation(project_path: str) -> Dict[str, Any]:
    path = os.path.join(project_path, ".opclog", "rollout_evaluation.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"rollout evaluation file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_rollout_decision(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    recommendation = str(evaluation.get("recommendation", "insufficient_data"))
    reason = str(evaluation.get("reason", ""))

    target_run_mode = "legacy_mode"
    target_gray_percent = 0
    rollout_action = "hold_legacy"

    if recommendation == "promote_skill_default":
        target_run_mode = "skill_mode"
        target_gray_percent = 100
        rollout_action = "promote_default"
    elif recommendation == "continue_gray":
        target_run_mode = "legacy_mode"
        target_gray_percent = 50
        rollout_action = "continue_gray"
    elif recommendation == "rollback_skill":
        target_run_mode = "legacy_mode"
        target_gray_percent = 0
        rollout_action = "rollback"
    elif recommendation == "insufficient_data":
        target_run_mode = "legacy_mode"
        target_gray_percent = 20
        rollout_action = "collect_more_data"

    rollback_plan = {
        "trigger_conditions": [
            "skill_failure_rate > max_skill_failure_rate",
            "skill_failure_rate > legacy_failure_rate + 0.15",
            "critical production incident linked to skill_mode",
        ],
        "immediate_actions": [
            "set OPC_RUN_MODE=legacy_mode",
            "set OPC_SKILL_GRAY_PERCENT=0",
            "restart current optimization session",
        ],
        "verification_commands": [
            "python -m pytest tests/test_graph.py -q",
            "python scripts/evaluate_rollout.py --project-path .",
        ],
    }

    return {
        "recommendation": recommendation,
        "reason": reason,
        "rollout_action": rollout_action,
        "target_run_mode": target_run_mode,
        "target_gray_percent": target_gray_percent,
        "env_plan": {
            "OPC_RUN_MODE": target_run_mode,
            "OPC_SKILL_GRAY_PERCENT": str(target_gray_percent),
        },
        "rollback_plan": rollback_plan,
    }


def decide_rollout_mode(project_path: str) -> Dict[str, Any]:
    evaluation = _load_rollout_evaluation(project_path)
    decision = build_rollout_decision(evaluation)

    out_path = os.path.join(project_path, ".opclog", "rollout_decision.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(decision, f, ensure_ascii=False, indent=2)

    return decision


def main() -> int:
    parser = argparse.ArgumentParser(description="Build rollout mode decision and rollback plan.")
    parser.add_argument("--project-path", type=str, default=".", help="Project path")
    args = parser.parse_args()

    project_path = os.path.abspath(args.project_path)
    decision = decide_rollout_mode(project_path)
    print("Rollout decision:")
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

