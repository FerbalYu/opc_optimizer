"""
Metrics Tracker — quantitative per-round metrics collection and persistence.

Inspired by autoresearch's results.tsv evolution archive.
Each round appends one JSON line to `.opclog/metrics.jsonl`.
"""

import json
import os
import time
import logging
import difflib
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger("opc.metrics_tracker")


def _count_diff_lines(project_path: str, modified_files: List[str]) -> dict:
    """Count lines added/removed by comparing .bak files with current files."""
    added = 0
    removed = 0
    for filepath in modified_files:
        abs_path = os.path.join(project_path, filepath)
        bak_path = abs_path + ".bak"
        if not (os.path.exists(abs_path) and os.path.exists(bak_path)):
            continue
        try:
            with open(bak_path, "r", encoding="utf-8", errors="replace") as f:
                old_lines = f.readlines()
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                new_lines = f.readlines()
            diff = list(difflib.unified_diff(old_lines, new_lines, lineterm=""))
            for line in diff:
                if line.startswith("+") and not line.startswith("+++"):
                    added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    removed += 1
        except Exception as e:
            logger.debug(f"Diff counting failed for {filepath}: {e}")
    return {"lines_added": added, "lines_removed": removed, "net_lines_delta": added - removed}


def collect_round_metrics(state: dict) -> dict:
    """Collect quantifiable metrics from the current round state.

    Returns a dict suitable for appending to metrics.jsonl.
    """
    project_path = state.get("project_path", "")
    modified_files = list(state.get("modified_files", []) or [])
    round_evaluation = state.get("round_evaluation", {}) or {}
    build_result = state.get("build_result", {}) or {}
    node_timings = state.get("node_timings", {}) or {}

    # Calculate round elapsed time
    round_start = state.get("round_start_time", 0)
    round_elapsed = round(time.time() - round_start, 2) if round_start > 0 else 0.0

    # Calculate total node time
    total_node_time = round(sum(node_timings.values()), 2) if node_timings else 0.0

    # Diff line counts
    diff_counts = _count_diff_lines(project_path, modified_files)

    # LLM cost (from class-level counters)
    llm_cost = 0.0
    llm_tokens = 0
    llm_calls = 0
    try:
        from utils.llm import LLMService
        llm_cost = round(LLMService._total_cost, 4)
        llm_tokens = LLMService._total_prompt_tokens + LLMService._total_completion_tokens
        llm_calls = LLMService._total_calls
    except Exception:
        pass

    is_rollback = (
        not build_result.get("build_passed", True)
        or bool(round_evaluation.get("low_value_round"))
    )

    return {
        "round": state.get("current_round", 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "value_score": round_evaluation.get("value_score", 0),
        "build_passed": bool(build_result.get("build_passed", True)),
        "test_passed": bool(build_result.get("test_passed", True)),
        "files_changed_count": len(modified_files),
        "lines_added": diff_counts["lines_added"],
        "lines_removed": diff_counts["lines_removed"],
        "net_lines_delta": diff_counts["net_lines_delta"],
        "round_elapsed_seconds": round_elapsed,
        "total_node_time_seconds": total_node_time,
        "node_timings": node_timings,
        "llm_cost_usd": llm_cost,
        "llm_total_tokens": llm_tokens,
        "llm_total_calls": llm_calls,
        "consecutive_no_improvements": state.get("consecutive_no_improvements", 0),
        "is_rollback": is_rollback,
        "objective_completed": bool(round_evaluation.get("objective_completed")),
    }


def append_metrics(project_path: str, metrics_row: dict) -> str:
    """Append a metrics row to `.opclog/metrics.jsonl`.

    Returns the path to the metrics file.
    """
    metrics_path = os.path.join(project_path, ".opclog", "metrics.jsonl")
    os.makedirs(os.path.dirname(metrics_path), exist_ok=True)
    with open(metrics_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(metrics_row, ensure_ascii=False) + "\n")
    logger.info(f"Metrics appended to {metrics_path} (round {metrics_row.get('round')})")
    return metrics_path


def load_metrics(project_path: str) -> List[dict]:
    """Load all metrics rows from `.opclog/metrics.jsonl`.

    Returns an empty list if the file does not exist.
    """
    metrics_path = os.path.join(project_path, ".opclog", "metrics.jsonl")
    if not os.path.exists(metrics_path):
        return []
    rows = []
    with open(metrics_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(f"Skipping malformed metrics line: {line[:80]}")
    return rows
