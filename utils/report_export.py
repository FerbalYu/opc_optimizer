"""Report export utility — merges all round reports into a single MD file (v2.3.0).

Provides a function to generate a comprehensive optimization report
that can be downloaded from the Web UI.
"""

import os
import glob
import logging

logger = logging.getLogger("opc.export")


def export_full_report(project_path: str, state: dict) -> str:
    """Merge all round reports into a single Markdown document.
    
    Args:
        project_path: Root path of the optimized project.
        state: Current optimizer state dict.

    Returns:
        Full markdown report as a string.
    """
    goal = state.get("optimization_goal", "N/A")
    total_rounds = state.get("current_round", 0)
    round_history = state.get("round_history", []) or []

    lines = [
        f"# OPC 优化报告",
        f"",
        f"> 自动生成 by OPC Local Optimizer",
        f"",
        f"## 📋 总览",
        f"",
        f"| 项目 | 值 |",
        f"|------|------|",
        f"| **优化目标** | {goal} |",
        f"| **总轮次** | {total_rounds} |",
        f"| **项目路径** | `{project_path}` |",
        f"",
    ]

    # Per-round summaries from round_history
    if round_history:
        lines.append("## 🔄 轮次摘要")
        lines.append("")
        for rh in round_history:
            r = rh.get("round", "?")
            files = rh.get("files_changed", [])
            summary = rh.get("summary", "N/A")
            suggestions = rh.get("suggestions", "")
            lines.append(f"### 第 {r} 轮")
            lines.append("")
            if files:
                lines.append(f"**修改文件**: {', '.join(f'`{f}`' for f in files)}")
            if summary:
                lines.append(f"**变更**: {summary}")
            if suggestions:
                lines.append(f"**建议**: {suggestions}")
            lines.append("")

    # Append full round report files if they exist
    report_files = state.get("round_reports", [])
    if report_files:
        lines.append("---")
        lines.append("")
        lines.append("## 📊 详细轮次报告")
        lines.append("")
        for rf in report_files:
            basename = os.path.basename(rf)
            try:
                if os.path.isfile(rf):
                    with open(rf, "r", encoding="utf-8") as f:
                        content = f.read()
                    lines.append(f"### 📄 {basename}")
                    lines.append("")
                    lines.append(content)
                    lines.append("")
                else:
                    lines.append(f"### 📄 {basename}")
                    lines.append(f"_(文件未找到: {rf})_")
                    lines.append("")
            except Exception as e:
                lines.append(f"### 📄 {basename}")
                lines.append(f"_(读取失败: {e})_")
                lines.append("")

    # Final suggestions
    suggestions = state.get("suggestions", "")
    if suggestions:
        lines.append("---")
        lines.append("")
        lines.append("## 💡 最终优化建议")
        lines.append("")
        lines.append(suggestions)
        lines.append("")

    return "\n".join(lines)
