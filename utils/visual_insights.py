"""Structured visual insights for the 3D companion UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(value)


def classify_file(path: str) -> dict:
    """Classify a changed file for the UI file wall."""
    normalized = str(path).replace("\\", "/").lstrip("./")
    lower = normalized.lower()
    name = Path(lower).name
    suffix = Path(lower).suffix

    if lower.startswith(("tests/", "test/")) or "/tests/" in lower or name.startswith("test_"):
        category = "test"
        label = "测试"
        color = "#f0883e"
    elif lower.startswith(("docs/", "doc/")) or suffix in {".md", ".rst", ".txt"}:
        category = "docs"
        label = "文档"
        color = "#bc8cff"
    elif lower.startswith(("ui/", "web/")) or suffix in {
        ".html",
        ".css",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".vue",
    }:
        category = "ui"
        label = "界面"
        color = "#39d2c0"
    elif name in {
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "tsconfig.json",
        "pytest.ini",
    } or suffix in {".toml", ".yaml", ".yml", ".json", ".ini"}:
        category = "config"
        label = "配置"
        color = "#58a6ff"
    elif suffix in {".py", ".go", ".rs", ".java", ".cs", ".cpp", ".c", ".h"}:
        category = "source"
        label = "源码"
        color = "#3fb950"
    else:
        category = "other"
        label = "其他"
        color = "#8b949e"

    return {
        "path": normalized,
        "category": category,
        "label": label,
        "color": color,
    }


def _file_wall(files: list[str]) -> dict:
    classified = [classify_file(path) for path in files]
    distribution: dict[str, int] = {}
    for item in classified:
        distribution[item["category"]] = distribution.get(item["category"], 0) + 1

    wall_items = []
    for item in classified:
        size = 1 + min(4, len(item["path"]) // 28)
        wall_items.append({**item, "weight": size})

    return {
        "total": len(classified),
        "distribution": distribution,
        "files": wall_items,
    }


def _score_health(round_metrics: dict, evaluation: dict, build_result: dict) -> tuple[int, list[str]]:
    score = int(round_metrics.get("value_score", evaluation.get("value_score", 0)) or 0)
    reasons: list[str] = []

    if round_metrics.get("files_changed_count", 0):
        score += 2
        reasons.append("产生了可见文件改动")
    else:
        score -= 3
        reasons.append("没有文件改动")

    if _as_bool(build_result.get("real_tests_ran", round_metrics.get("real_tests_ran")), True):
        score += 2
        reasons.append("运行了真实验证")
    else:
        score -= 2
        reasons.append("未运行真实验证")

    if build_result.get("validation_mode") == "static_fallback":
        score -= 2
        reasons.append("使用了静态降级验证")

    if not _as_bool(round_metrics.get("build_passed", build_result.get("build_passed")), True):
        score -= 3
        reasons.append("构建未通过")
    if not _as_bool(round_metrics.get("test_passed", build_result.get("test_passed")), True):
        score -= 3
        reasons.append("测试未通过")

    if evaluation.get("low_value_round"):
        score -= 2
        reasons.append("本轮被判定为低价值")
    if evaluation.get("readonly_violations"):
        score -= 5
        reasons.append("触碰了只读文件")
    if round_metrics.get("files_changed_count", 0) > 5:
        score -= 1
        reasons.append("改动范围偏大")

    return max(0, min(10, score)), reasons[:5]


def _value_label(score: int, evaluation: dict, build_result: dict) -> str:
    if not _as_bool(build_result.get("test_passed", True), True):
        return "需要人工介入"
    if evaluation.get("low_value_round"):
        return "原地打转"
    if score >= 8:
        return "明显提升"
    if score >= 5:
        return "小幅提升"
    if score >= 3:
        return "不稳定"
    return "原地打转"


def _prompt_microscope(state: dict, build_result: dict, evaluation: dict) -> list[dict]:
    contract = state.get("round_contract", {}) or {}
    return [
        {
            "name": "中文可见输出",
            "status": "active",
            "detail": "计划、报告、建议和 UI 文案要求使用简体中文。",
        },
        {
            "name": "协议保持英文",
            "status": "active",
            "detail": "SEARCH/REPLACE、JSON key、路径和命令保持机器可解析。",
        },
        {
            "name": "修改范围约束",
            "status": "active" if contract.get("target_files") else "watch",
            "detail": "已声明目标文件。" if contract.get("target_files") else "本轮目标文件不够明确。",
        },
        {
            "name": "真实验证约束",
            "status": "active" if build_result.get("real_tests_ran", True) else "warn",
            "detail": "真实测试已运行。" if build_result.get("real_tests_ran", True) else "需要补跑真实测试。",
        },
        {
            "name": "低价值拦截",
            "status": "warn" if evaluation.get("low_value_round") else "active",
            "detail": "本轮需要重新规划。" if evaluation.get("low_value_round") else "本轮未触发低价值拦截。",
        },
    ]


def _next_actions(score: int, evaluation: dict, build_result: dict) -> list[dict]:
    actions = []
    if not build_result.get("test_passed", True):
        actions.append({"label": "只修测试失败", "kind": "test_fix"})
    if build_result.get("validation_mode") == "static_fallback":
        actions.append({"label": "补跑真实验证", "kind": "verify"})
    if evaluation.get("low_value_round") or score < 5:
        actions.append({"label": "重新规划下一轮", "kind": "replan"})
    if score >= 7:
        actions.append({"label": "生成 PR 描述", "kind": "pr_summary"})
    actions.append({"label": "查看风险文件", "kind": "risk_files"})
    return actions[:4]


def build_round_insight(state: dict, round_metrics: dict | None = None) -> dict:
    """Build a compact insight payload for the visual companion."""
    metrics = round_metrics or {}
    evaluation = state.get("round_evaluation", {}) or {}
    build_result = state.get("build_result", {}) or {}
    files = list(state.get("modified_files", []) or [])
    score, reasons = _score_health(metrics, evaluation, build_result)
    label = _value_label(score, evaluation, build_result)

    return {
        "round": state.get("current_round", metrics.get("round", 1)),
        "health_score": score,
        "value_label": label,
        "health_reasons": reasons,
        "value_curve_point": {
            "round": state.get("current_round", metrics.get("round", 1)),
            "score": score,
            "label": label,
            "value_score": metrics.get("value_score", evaluation.get("value_score", 0)),
        },
        "file_wall": _file_wall(files),
        "prompt_microscope": _prompt_microscope(state, build_result, evaluation),
        "next_actions": _next_actions(score, evaluation, build_result),
    }
