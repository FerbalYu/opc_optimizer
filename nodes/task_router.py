"""Task Router Node — Dynamic Complexity Classification (Opt-1).

Runs BEFORE plan_node as the very first node in the LangGraph workflow.
Classifies the current round's intent into low / medium / high complexity
without any LLM calls (pure rule-based, ~0ms overhead).

low    → fast_path=True : skip full build + UI screenshot validation
medium → full pipeline (default)
high   → full pipeline with extra safety checks
"""

import logging
import re
from state import OptimizerState

logger = logging.getLogger("opc.task_router")

# ── Keywords that suggest a trivially small change ─────────────────────────
_LOW_COMPLEXITY_KEYWORDS = [
    # English
    "fix typo", "typo", "rename", "update comment", "update docstring",
    "add comment", "remove comment", "update readme", "fix comment",
    "update changelog", "bump version", "update version",
    "formatting", "whitespace", "indent", "indentation",
    "remove unused import", "remove unused variable",
    "update copyright", "update license",
    # Chinese
    "修改注释", "修改拼写", "更新注释", "删除无用导入", "删除无用变量",
    "格式化", "更新版本", "修改文案", "改名", "重命名",
]

# ── Keywords that suggest cross-module architectural work ───────────────────
_HIGH_COMPLEXITY_KEYWORDS = [
    "refactor", "architecture", "architect", "redesign", "rewrite",
    "migrate", "extract", "split", "merge modules", "dependency injection",
    "add feature", "new feature", "add module", "add service",
    "database schema", "api design", "breaking change",
    "性能优化", "架构重构", "重写", "迁移", "拆分", "合并模块", "新功能", "新特性",
]


def _classify(goal: str, current_round: int) -> str:
    """Return 'low', 'medium', or 'high' for a given goal string."""
    goal_lower = goal.lower()

    # High is checked first — it overrides low keywords
    for kw in _HIGH_COMPLEXITY_KEYWORDS:
        if kw in goal_lower:
            return "high"

    # Low: must match a keyword AND be a single-sentence goal
    word_count = len(goal.split())
    for kw in _LOW_COMPLEXITY_KEYWORDS:
        if kw in goal_lower:
            if word_count <= 20:   # short, focused goal
                return "low"
            break  # keyword matched but goal is complex

    return "medium"


def task_router_node(state: OptimizerState) -> OptimizerState:
    """Classify task complexity and set fast_path flag."""
    logger.info("--- 🚦 TASK ROUTER ---")

    goal = state.get("optimization_goal", "")
    current_round = state.get("current_round", 1)
    llm_config = state.get("llm_config", {}) or {}

    complexity = _classify(goal, current_round)
    fast_path = (complexity == "low")

    # Respect explicit override from llm_config (e.g., for testing)
    if llm_config.get("force_complexity"):
        complexity = llm_config["force_complexity"]
        fast_path = (complexity == "low")

    state["task_complexity"] = complexity
    state["fast_path"] = fast_path

    logger.info(
        f"Round {current_round}: complexity={complexity}, fast_path={fast_path} "
        f"| goal={goal[:80]!r}"
    )

    try:
        from ui.web_server import emit
        emit("task_complexity", {
            "round": current_round,
            "complexity": complexity,
            "fast_path": fast_path,
            "goal": goal[:120],
        })
    except Exception:
        pass

    return state
