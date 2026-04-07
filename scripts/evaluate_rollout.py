"""Evaluate skill rollout quality from `.opclog/metrics.jsonl`."""

import argparse
import json
import os
import sys
from typing import Dict, List


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_project_root_on_path() -> None:
    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)


def _is_failure(row: dict) -> bool:
    if str(row.get("failure_type", "none")).lower() != "none":
        return True
    if not bool(row.get("build_passed", True)):
        return True
    if not bool(row.get("test_passed", True)):
        return True
    return False


def _failure_rate(rows: List[dict]) -> float:
    if not rows:
        return 0.0
    failed = sum(1 for r in rows if _is_failure(r))
    return failed / len(rows)


def evaluate_rollout(
    project_path: str,
    min_rounds: int = 5,
    max_skill_failure_rate: float = 0.20,
    promote_min_skill_share: float = 0.50,
) -> Dict[str, object]:
    """Evaluate rollout and return a structured recommendation."""
    _ensure_project_root_on_path()
    from utils.metrics_tracker import load_metrics

    rows = load_metrics(project_path)
    total = len(rows)
    skill_rows = [r for r in rows if r.get("run_mode") == "skill_mode"]
    legacy_rows = [r for r in rows if r.get("run_mode") == "legacy_mode"]

    skill_failure_rate = _failure_rate(skill_rows)
    legacy_failure_rate = _failure_rate(legacy_rows)
    skill_share = (len(skill_rows) / total) if total else 0.0

    recommendation = "continue_gray"
    reason = "default recommendation"
    if total < min_rounds:
        recommendation = "insufficient_data"
        reason = f"not enough rounds: {total} < {min_rounds}"
    elif not skill_rows:
        recommendation = "continue_gray"
        reason = "no skill_mode samples"
    elif skill_failure_rate > max_skill_failure_rate:
        recommendation = "rollback_skill"
        reason = "skill failure rate exceeds max threshold"
    elif skill_failure_rate > legacy_failure_rate + 0.15:
        recommendation = "rollback_skill"
        reason = "skill failure rate significantly worse than legacy"
    elif skill_share >= promote_min_skill_share and skill_failure_rate <= legacy_failure_rate + 0.05:
        recommendation = "promote_skill_default"
        reason = "skill share and quality are stable enough"

    result = {
        "project_path": project_path,
        "total_rounds": total,
        "skill_rounds": len(skill_rows),
        "legacy_rounds": len(legacy_rows),
        "skill_share": round(skill_share, 4),
        "skill_failure_rate": round(skill_failure_rate, 4),
        "legacy_failure_rate": round(legacy_failure_rate, 4),
        "recommendation": recommendation,
        "reason": reason,
        "thresholds": {
            "min_rounds": min_rounds,
            "max_skill_failure_rate": max_skill_failure_rate,
            "promote_min_skill_share": promote_min_skill_share,
        },
    }

    out_path = os.path.join(project_path, ".opclog", "rollout_evaluation.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate skill rollout from metrics data.")
    parser.add_argument(
        "--project-path",
        type=str,
        default=".",
        help="Project path containing .opclog/metrics.jsonl",
    )
    parser.add_argument("--min-rounds", type=int, default=5, help="Minimum rounds for valid decision")
    parser.add_argument(
        "--max-skill-failure-rate",
        type=float,
        default=0.20,
        help="Max acceptable skill failure rate before rollback",
    )
    parser.add_argument(
        "--promote-min-skill-share",
        type=float,
        default=0.50,
        help="Minimum skill share required before promoting skill_mode default",
    )
    args = parser.parse_args()

    result = evaluate_rollout(
        project_path=os.path.abspath(args.project_path),
        min_rounds=args.min_rounds,
        max_skill_failure_rate=args.max_skill_failure_rate,
        promote_min_skill_share=args.promote_min_skill_share,
    )

    print("Rollout evaluation summary:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

