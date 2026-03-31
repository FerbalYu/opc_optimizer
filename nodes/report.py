import json
import os
import logging
from state import OptimizerState
from utils.file_ops import write_to_file
from utils.git_ops import git_auto_commit
from utils.checkpoint import save_checkpoint
from utils.llm import LLMService

logger = logging.getLogger("opc.report")


def report_node(state: OptimizerState) -> OptimizerState:
    logger.info("--- REPORT PHASE ---")
    current_round = state.get("current_round", 1)
    project_path = state["project_path"]
    round_evaluation = state.get("round_evaluation", {}) or {}
    diff_evidence = ((state.get("build_result", {}) or {}).get("diff_evidence")) or "No file-level diff evidence available."

    # ── Collect & persist metrics (autoresearch-inspired) ─────────
    round_metrics = {}
    try:
        from utils.metrics_tracker import collect_round_metrics, append_metrics
        round_metrics = collect_round_metrics(state)
        append_metrics(project_path, round_metrics)
        state["round_metrics"] = round_metrics
        logger.info(f"Round metrics collected: value_score={round_metrics.get('value_score')}, "
                     f"lines_added={round_metrics.get('lines_added')}, "
                     f"elapsed={round_metrics.get('round_elapsed_seconds')}s")
    except Exception as e:
        logger.warning(f"Metrics collection failed: {e}")

    logger.info(f"Generating summary report for Round {current_round}...")

    report_content = f"""# OPC Round Report - Round {current_round}
## Goal
{state.get("optimization_goal")}

## Plan
{state.get("current_plan")}

## Code Diff Summary
{state.get("code_diff")}

## Test Results
```text
{state.get("test_results")}
```

## Diff Evidence
{diff_evidence}

## Round Evaluation
```json
{json.dumps(round_evaluation, ensure_ascii=False, indent=2)}
```

## Suggestions For Next Round
{state.get("suggestions")}

## Node Timings
"""

    timings = state.get("node_timings", {}) or {}
    if timings:
        for node_name, elapsed in timings.items():
            report_content += f"- **{node_name}**: {elapsed}s\n"
    else:
        report_content += "_(no timing data)_\n"

    # Handle tests mocking LLMService variables globally
    total_cost = getattr(LLMService, "_total_cost", 0.0)
    if hasattr(total_cost, "_mock_name"):  # it's a MagicMock
        total_cost = 0.0
    total_calls = getattr(LLMService, "_total_calls", 0)
    if hasattr(total_calls, "_mock_name"):
        total_calls = 0
    prompt_tokens = getattr(LLMService, "_total_prompt_tokens", 0)
    if hasattr(prompt_tokens, "_mock_name"):
        prompt_tokens = 0
    comp_tokens = getattr(LLMService, "_total_completion_tokens", 0)
    if hasattr(comp_tokens, "_mock_name"):
        comp_tokens = 0

    report_content += f"""
## API Cost
- Round cumulative: ${total_cost:.4f} USD
- Total calls: {total_calls}
- Total tokens: {prompt_tokens + comp_tokens:,}
"""

    # ── Metrics section (autoresearch-inspired evolution archive) ──
    if round_metrics:
        llm_cost_usd = round_metrics.get('llm_cost_usd', 0)
        if hasattr(llm_cost_usd, "_mock_name"): llm_cost_usd = 0.0
        
        round_elapsed = round_metrics.get('round_elapsed_seconds', 0)
        if hasattr(round_elapsed, "_mock_name"): round_elapsed = 0.0

        report_content += f"""
## Metrics
| Metric | Value |
|--------|-------|
| Value Score | {round_metrics.get('value_score', 'N/A')}/10 |
| Files Changed | {round_metrics.get('files_changed_count', 0)} |
| Lines Added | +{round_metrics.get('lines_added', 0)} |
| Lines Removed | -{round_metrics.get('lines_removed', 0)} |
| Net Delta | {round_metrics.get('net_lines_delta', 0)} |
| Round Elapsed | {round_elapsed:.1f}s |
| LLM Cost | ${llm_cost_usd:.4f} |
| Rollback | {'Yes' if round_metrics.get('is_rollback') else 'No'} |
"""

    # Write report to external workspace (Opt-6)
    try:
        from utils.workspace import workspace_path
        report_path = workspace_path(project_path, "reports", f"round_{current_round}.md")
    except Exception:
        report_path = os.path.join(project_path, ".opclog", "rounds", f"round_{current_round}.md")
    write_to_file(report_path, report_content)

    reports = state.get("round_reports", []) or []
    reports.append(report_path)
    state["round_reports"] = reports

    diff_summary = state.get("code_diff", "")
    git_auto_commit(project_path, current_round, summary=diff_summary)

    save_checkpoint(project_path, state)

    try:
        from utils.trace_logger import get_trace_logger
        get_trace_logger().save_round(project_path, current_round)
    except Exception:
        pass

    round_summary = {
        "round": current_round,
        "summary": (state.get("code_diff", "") or "")[:300],
        "files_changed": list(state.get("modified_files", []) or []),
        "suggestions": (state.get("suggestions", "") or "")[:200],
        "evaluation": round_evaluation,
        "metrics": round_metrics,
    }
    history = list(state.get("round_history", []) or [])
    history.append(round_summary)
    state["round_history"] = history

    try:
        from utils.context_pruner import condense_history
        condensed = condense_history(
            round_history=history,
            llm=LLMService(),
            current_round=current_round,
            window_size=2,
        )
        state["condensed_history"] = condensed
        logger.info(f"Context condensed: {len(condensed)} chars for {len(history)} rounds")
    except Exception as e:
        logger.warning(f"Context condensation failed: {e}")
        if "condensed_history" not in state:
            state["condensed_history"] = ""

    try:
        from ui.web_server import emit
        emit("round_history_update", {
            "round": current_round,
            "plan_summary": (state.get("current_plan", "") or "")[:500],
            "diff_summary": (state.get("code_diff", "") or "")[:500],
            "suggestions": (state.get("suggestions", "") or "")[:500],
            "files_changed": list(state.get("modified_files", []) or []),
            "timings": state.get("node_timings", {}),
            "evaluation": round_evaluation,
        })
        # Emit metrics for Web UI dashboard trend chart
        if round_metrics:
            emit("metrics_update", {"round": current_round, "metrics": round_metrics})
    except Exception:
        pass

    logger.info(f"Report generated and saved to {report_path}")
    return state
