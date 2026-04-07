"""Skill routing primitives for Phase 2.

This module computes a stable skill execution plan from runtime context.
It is intentionally side-effect free so it can be adopted incrementally.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class SkillRoutePlan:
    """Resolved routing result for one optimization round."""

    mode: str
    skill_chain: List[str]
    router_decision: str
    fallback_mode: str = "legacy_mode"
    fallback_reason: str = ""
    jump_conditions: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "skill_chain": list(self.skill_chain),
            "router_decision": self.router_decision,
            "fallback_mode": self.fallback_mode,
            "fallback_reason": self.fallback_reason,
            "jump_conditions": dict(self.jump_conditions),
        }


def route_skills(
    goal: str,
    run_mode: str = "legacy_mode",
    project_profile: Dict[str, Any] | None = None,
    failure_type: str = "none",
) -> SkillRoutePlan:
    """Route to a skill plan based on goal/profile/failure history.

    Routing policy (Phase 2 baseline):
    - Non-`skill_mode` runs remain on legacy linear flow.
    - In `skill_mode`, default chain is plan->execute->test->report.
    - For low-risk doc-only goals with no recent failures, test can be skipped.
    - For recent failures, test is always retained.
    """
    profile = project_profile or {}
    normalized_mode = run_mode if run_mode in ("legacy_mode", "skill_mode") else "legacy_mode"
    normalized_failure = (failure_type or "none").strip().lower()
    normalized_goal = (goal or "").strip().lower()

    if normalized_mode != "skill_mode":
        return SkillRoutePlan(
            mode="legacy_mode",
            skill_chain=["plan", "execute", "test", "report"],
            router_decision="skill_router:legacy_passthrough",
            fallback_mode="legacy_mode",
            fallback_reason="run_mode_not_skill_mode",
            jump_conditions={},
        )

    languages = [str(x).lower() for x in profile.get("languages", [])]
    is_doc_goal = any(
        key in normalized_goal
        for key in ("doc", "docs", "readme", "comment", "注释", "文档")
    )
    low_risk_profile = not any(lang in {"c", "cpp", "rust"} for lang in languages)
    has_recent_failures = normalized_failure not in ("", "none")

    chain = ["plan", "execute", "test", "report"]
    jump_conditions: Dict[str, str] = {}
    decision = "skill_router:default_chain"
    if is_doc_goal and low_risk_profile and not has_recent_failures:
        chain = ["plan", "execute", "report"]
        jump_conditions["execute"] = "if_doc_only_then_skip_test"
        decision = "skill_router:doc_only_fast_path"
    elif has_recent_failures:
        decision = f"skill_router:failure_guard({normalized_failure})"

    return SkillRoutePlan(
        mode="skill_mode",
        skill_chain=chain,
        router_decision=decision,
        fallback_mode="legacy_mode",
        fallback_reason="router_failure_or_guard",
        jump_conditions=jump_conditions,
    )

