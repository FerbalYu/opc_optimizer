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
                "shutdown_in_seconds": 15,
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
        stop_reason = "达到最大轮数"
    elif round_evaluation.get("low_value_round"):
        stop_reason = "因连续低价值或偏离目标的轮次而停止"
    else:
        stop_reason = "用户停止或触发无改进保护"

    report = f"""# OPC 最终报告
## 概览
- 总轮数: {current_round}
- 优化目标: {state.get("optimization_goal")}
- 停止原因: {stop_reason}

## 最终代码改动
{state.get("code_diff", "无改动")}

## 最终建议
{state.get("suggestions", "无建议")}

## 最终轮次评估
{round_evaluation}

## 最终 Diff 证据
{((state.get("build_result", {}) or {}).get("diff_evidence")) or "没有可用的文件级 diff 证据。"}

## 轮次报告
{chr(10).join(f"- {r}" for r in (state.get("round_reports") or []))}
"""

    # Write to external workspace (Opt-6)
    try:
        from utils.workspace import workspace_path

        report_path = workspace_path(project_path, "reports", "final_report.md")
    except Exception:
        report_path = os.path.join(project_path, ".opclog", "final_report.md")
    write_to_file(report_path, report)
    print(f"最终报告已保存到 {report_path}")


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

        if os.environ.get("OPC_VISUAL_COMPANION", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            print(
                f"\n3D 可视化副屏已记录第 {current_round}/{max_rounds} 轮，"
                "继续由 CLI 接收下一步操作。"
            )
            return False

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
            f"\n正在等待 Web UI 输入（第 {current_round}/{max_rounds} 轮，30 秒超时）..."
        )
        # 30 seconds: matches original design — auto-continue if no action taken
        cmd = wait_for_user_command(timeout=30)

        if cmd is None:
            print("Web UI 30 秒超时，自动继续下一轮...")
            state["should_stop"] = False
            state["current_round"] = current_round + 1
            return True

        action = cmd.get("action", "continue")

        if action == "continue":
            state["should_stop"] = False
            print("Web UI：继续下一轮")
        elif action == "stop":
            state["should_stop"] = True
            print("Web UI：用户请求停止")
            _generate_final_report(state)
        elif action == "skip":
            state["should_stop"] = False
            print("Web UI：跳过当前轮结果")
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
                        print(f"  已恢复: {filepath}")
                state["modified_files"] = []
                state["code_diff"] = "用户已回滚"
            state["should_stop"] = False
            print("Web UI：已回滚改动")
        elif action == "adjust_goal":
            new_goal = _validate_goal(cmd.get("goal", ""))
            if new_goal:
                state["optimization_goal"] = new_goal
                print(f"Web UI：优化目标已更新为: {new_goal}")
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
                    "shutdown_in_seconds": 15,
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
        if os.environ.get("OPC_VISUAL_COMPANION", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            try:
                from ui.web_server import emit, _clients

                if _clients:
                    emit(
                        "round_end",
                        {
                            "round": current_round,
                            "timings": state.get("node_timings", {}) or {},
                        },
                    )
            except ImportError:
                pass
        if replan_required:
            print(
                "\n自动模式：下一轮会重新规划，因为本轮低价值或偏离目标。"
            )
        print(
            f"\n自动模式：继续进入第 {current_round + 1}/{max_rounds} 轮。"
        )
        state["should_stop"] = False
        state["current_round"] = current_round + 1
        return state

    if _try_web_ui_interact(state):
        return state

    print(f"\n已完成第 {current_round}/{max_rounds} 轮。")
    print("可选操作:")
    print("  [c] 继续下一轮")
    print("  [s] 停止优化")
    print("  [a] 调整优化目标")

    while True:
        try:
            choice = input("\n操作 [c/s/a]: ").strip().lower()

            if choice == "c" or choice == "":
                state["should_stop"] = False
                break
            if choice == "s":
                state["should_stop"] = True
                print("用户请求停止循环。")
                _generate_final_report(state)
                break
            if choice == "a":
                new_goal = _validate_goal(
                    input("请输入新的优化目标: ").strip()
                )
                if new_goal:
                    state["optimization_goal"] = new_goal
                    print(f"优化目标已更新为: {new_goal}")
                state["should_stop"] = False
                break
            print("无效选择。请输入 'c'、's' 或 'a'。")
        except EOFError:
            print("\n检测到非交互环境，自动继续...")
            state["should_stop"] = False
            break

    if not state["should_stop"]:
        state["current_round"] = current_round + 1

    return state
