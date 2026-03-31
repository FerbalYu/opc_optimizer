import os
import shutil
import re
import logging
from state import OptimizerState
from utils.file_ops import write_to_file
from utils.constants import MAX_GOAL_LENGTH, MAX_INPUT_LENGTH

logger = logging.getLogger("opc.interact")

# 危险模式检测（用于防御prompt注入）
_DANGEROUS_PATTERNS = [
    re.compile(r"__import__"),
    re.compile(r"\beval\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"\$\{.*\}"),
    re.compile(r"<script[^>]*>"),
    re.compile(r"javascript:"),
]


def _sanitize_input(text: str, max_length: int = MAX_INPUT_LENGTH) -> str:
    """验证并清理用户输入。

    Args:
        text: 用户输入文本
        max_length: 最大允许长度

    Returns:
        清理后的安全文本
    """
    if not text:
        return ""
    text = text.strip()
    if len(text) > max_length:
        text = text[:max_length]
        logger.warning(f"Input truncated to {max_length} characters")
    return text


def _validate_goal(goal: str) -> str:
    """验证并清理用户输入的goal，防止prompt注入攻击。

    Args:
        goal: 用户输入的优化目标

    Returns:
        清理后的安全goal
    """
    if not goal:
        return ""
    goal = _sanitize_input(goal, MAX_GOAL_LENGTH)
    # 检测潜在危险模式
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(goal):
            goal = pattern.sub("***", goal)
            logger.warning(
                "Detected potentially dangerous content, it has been sanitized"
            )
    return goal


def _emit_stop_events(state: OptimizerState, stopped_round: int) -> None:
    """Emit round_end + optimization_complete to any connected WebUI clients."""
    try:
        from ui.web_server import emit, _clients

        if not _clients:
            return
        timings_data = state.get("node_timings", {}) or {}
        emit("round_end", {"round": stopped_round, "timings": timings_data})
        emit(
            "optimization_complete",
            {
                "total_rounds": stopped_round,
                "goal": state.get("optimization_goal", ""),
                "final_diff": state.get("code_diff", ""),
                "suggestions": state.get("suggestions", ""),
                "reports": state.get("round_reports", []),
                "shutdown_in_seconds": 0,
            },
        )
    except Exception:
        pass


def _generate_final_report(state: OptimizerState) -> None:
    """Generate a final summary report when the optimization loop ends."""
    project_path = state["project_path"]
    current_round = state.get("current_round", 1)
    round_evaluation = state.get("round_evaluation", {}) or {}

    if current_round >= state.get("max_rounds", 5):
        stop_reason = "Reached max rounds"
    elif round_evaluation.get("low_value_round"):
        stop_reason = "Stopped after repeated low-value or misaligned rounds"
    else:
        stop_reason = "Stopped by user or no-improvement guard"

    report = f"""# OPC Final Report
## Overview
- Total rounds: {current_round}
- Optimization goal: {state.get("optimization_goal")}
- Stop reason: {stop_reason}

## Final Code Diff
{state.get("code_diff", "No changes")}

## Final Suggestions
{state.get("suggestions", "No suggestions")}

## Final Round Evaluation
{round_evaluation}

## Final Diff Evidence
{((state.get("build_result", {}) or {}).get("diff_evidence")) or "No file-level diff evidence available."}

## Round Reports
{chr(10).join(f"- {r}" for r in (state.get("round_reports") or []))}
"""

    # Write to external workspace (Opt-6)
    try:
        from utils.workspace import workspace_path

        report_path = workspace_path(project_path, "reports", "final_report.md")
    except Exception:
        report_path = os.path.join(project_path, ".opclog", "final_report.md")
    write_to_file(report_path, report)
    print(f"Final report saved to {report_path}")


def _try_web_ui_interact(state: OptimizerState) -> bool:
    """Try to get user input from Web UI. Returns True if handled.

    This function owns the round_end and optimization_complete WebSocket events.
    They are emitted here (not in graph.py's wrapper) because interact_node is
    the only place that knows the outcome of the WebSocket wait.
    """
    try:
        from ui.web_server import wait_for_user_command, emit, _clients

        if not _clients:
            return False

        current_round = state.get("current_round", 1)
        max_rounds = state.get("max_rounds", 5)
        timings_data = state.get("node_timings", {}) or {}

        # Tell the frontend this round is done and we're waiting for input.
        # round_end carries the timing data so the UI can render the round card.
        emit(
            "round_end",
            {
                "round": current_round,
                "timings": timings_data,
            },
        )

        emit(
            "awaiting_input",
            {
                "round": current_round,
                "max_rounds": max_rounds,
                "timeout_seconds": 30,
                "options": ["continue", "stop", "skip", "rollback", "adjust_goal"],
            },
        )

        print(
            f"\nWaiting for input from Web UI (round {current_round}/{max_rounds}, 30s timeout)..."
        )
        # 30 seconds: matches original design — auto-continue if no action taken
        cmd = wait_for_user_command(timeout=30)

        if cmd is None:
            print("Web UI timeout (30s). Auto-continuing to next round...")
            state["should_stop"] = False
            state["current_round"] = current_round + 1
            return True

        action = cmd.get("action", "continue")

        if action == "continue":
            state["should_stop"] = False
            print("Web UI: Continue to next round")
        elif action == "stop":
            state["should_stop"] = True
            print("Web UI: User requested stop")
            _generate_final_report(state)
        elif action == "skip":
            state["should_stop"] = False
            print("Web UI: Skipping current round results")
            state["current_round"] = current_round + 1
            return True
        elif action == "rollback":
            modified_files = state.get("modified_files", []) or []
            project_path = state.get("project_path", "")
            if modified_files and project_path:
                import shutil as _shutil

                for filepath in modified_files:
                    abs_path = os.path.join(project_path, filepath)
                    bak_path = abs_path + ".bak"
                    if os.path.exists(bak_path):
                        _shutil.copy2(bak_path, abs_path)
                        print(f"  Restored: {filepath}")
                state["modified_files"] = []
                state["code_diff"] = "Rolled back by user"
            state["should_stop"] = False
            print("Web UI: Rolled back changes")
        elif action == "adjust_goal":
            new_goal = _validate_goal(cmd.get("goal", ""))
            if new_goal:
                state["optimization_goal"] = new_goal
                print(f"Web UI: Goal updated to: {new_goal}")
            state["should_stop"] = False
        else:
            state["should_stop"] = False

        if not state["should_stop"]:
            state["current_round"] = current_round + 1
        else:
            # Emit optimization_complete so the frontend shows the finish screen
            emit(
                "optimization_complete",
                {
                    "total_rounds": current_round,
                    "goal": state.get("optimization_goal", ""),
                    "final_diff": state.get("code_diff", ""),
                    "suggestions": state.get("suggestions", ""),
                    "reports": state.get("round_reports", []),
                    "shutdown_in_seconds": 0,
                },
            )

        return True
    except ImportError:
        return False


def interact_node(state: OptimizerState) -> OptimizerState:
    print("\n" + "=" * 50)
    print("      INTERACT PHASE - WAITING FOR USER INPUT")
    print("=" * 50)

    current_round = state.get("current_round", 1)
    max_rounds = state.get("max_rounds", 5)
    round_evaluation = state.get("round_evaluation", {}) or {}

    # ── 唯一的自动停止条件：跑满 max_rounds ──
    if current_round >= max_rounds:
        print(f"\n✅ Reached max rounds ({max_rounds}). Optimization complete.")
        state["should_stop"] = True
        _generate_final_report(state)
        _emit_stop_events(state, current_round)
        return state

    modified_files = state.get("modified_files", []) or []
    code_diff = state.get("code_diff", "")
    no_effective_changes = not modified_files and (
        not code_diff
        or "No changes" in code_diff
        or code_diff.startswith("SKIP")
        or all(
            line.strip().startswith("SKIP") or line.strip().startswith("BLOCKED")
            for line in code_diff.strip().splitlines()
            if line.strip()
        )
    )

    low_value_round = bool(round_evaluation.get("low_value_round"))
    replan_required = bool(round_evaluation.get("replan_required"))

    # 统计无改进轮次（仅用于信息展示，不触发停止）
    no_improvements = state.get("consecutive_no_improvements", 0)
    if no_effective_changes or low_value_round:
        no_improvements += 1
        state["consecutive_no_improvements"] = no_improvements

        # 针对执行节点失败/无解析改动作专门提示
        if code_diff == "No changes parsed from LLM output.":
            reason_text = "检测到 AI 未输出可用代码，本轮执行轮空拦截 (Laziness / No parsable action)"
        else:
            reason_text = (
                "; ".join(round_evaluation.get("reasons", [])[:3])
                or "No effective code changes"
            )

        print(
            f"\n⚠️  Round {current_round} was low-value/non-improving "
            f"(consecutive count: {no_improvements}). Continuing to next round..."
        )
        print(f"   Reasons: {reason_text}")
        print(f"   Remaining rounds: {max_rounds - current_round}")
    else:
        state["consecutive_no_improvements"] = 0
        no_improvements = 0

    # ── 注意：绝不提前停止，始终跑满 max_rounds ──

    if state.get("auto_mode", False):
        if replan_required:
            print(
                "\nAuto-mode: next round will replan because this round was low-value or misaligned."
            )
        print(
            f"\nAuto-mode: Continuing to next round (Round {current_round + 1}/{max_rounds})."
        )
        state["should_stop"] = False
        state["current_round"] = current_round + 1
        return state

    if _try_web_ui_interact(state):
        return state

    print(f"\nCompleted Round {current_round}/{max_rounds}.")
    print("Options:")
    print("  [c] Continue to next round")
    print("  [s] Stop optimization")
    print("  [a] Adjust optimization goal")

    while True:
        try:
            choice = input("\nAction [c/s/a]: ").strip().lower()

            if choice == "c" or choice == "":
                state["should_stop"] = False
                break
            if choice == "s":
                state["should_stop"] = True
                print("User requested to stop the loop.")
                _generate_final_report(state)
                break
            if choice == "a":
                new_goal = _validate_goal(
                    input("Enter new optimization goal: ").strip()
                )
                if new_goal:
                    state["optimization_goal"] = new_goal
                    print(f"Goal updated to: {new_goal}")
                state["should_stop"] = False
                break
            print("Invalid choice. Please enter 'c', 's', or 'a'.")
        except EOFError:
            print("\nNon-interactive environment detected. Auto-continuing...")
            state["should_stop"] = False
            break

    if not state["should_stop"]:
        state["current_round"] = current_round + 1

    return state
