"""Unified preamble injection helpers for skill workflow prompts."""

import time
from typing import Any, Dict, Optional


def _build_context(state: dict, project_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    profile = project_profile or {}
    session_id = state.get("session_id") or f"opc-{int(time.time() * 1000)}"
    round_number = int(state.get("current_round", 1) or 1)
    round_id = f"round-{round_number}"

    llm_config = state.get("llm_config", {}) or {}
    context = {
        "session_id": session_id,
        "round_id": round_id,
        "run_mode": state.get("run_mode", "legacy_mode"),
        "project_profile": {
            "type": profile.get("type", "unknown"),
            "languages": list(profile.get("languages", []) or []),
            "detected_by": profile.get("detected_by", "unknown"),
        },
        "config": {
            "auto_mode": bool(state.get("auto_mode", False)),
            "dry_run": bool(state.get("dry_run", False)),
            "skip_plan_review": bool(
                ((state.get("ui_preferences", {}) or {}).get("skip_plan_review", False))
            ),
            "timeout": llm_config.get("timeout", 120),
        },
    }
    return context


def _render_preamble(context: Dict[str, Any]) -> str:
    profile = context.get("project_profile", {}) or {}
    config = context.get("config", {}) or {}
    langs = profile.get("languages", [])
    lang_text = ", ".join(str(x) for x in langs) if langs else "unknown"
    return (
        "## Unified Skill Preamble\n"
        f"- session_id: {context.get('session_id', '')}\n"
        f"- round_id: {context.get('round_id', '')}\n"
        f"- run_mode: {context.get('run_mode', 'legacy_mode')}\n"
        f"- profile: type={profile.get('type', 'unknown')}, languages={lang_text}, detected_by={profile.get('detected_by', 'unknown')}\n"
        f"- config: auto_mode={config.get('auto_mode', False)}, dry_run={config.get('dry_run', False)}, "
        f"skip_plan_review={config.get('skip_plan_review', False)}, timeout={config.get('timeout', 120)}\n"
    )


def inject_skill_preamble(
    state: dict, project_profile: Optional[Dict[str, Any]] = None
) -> str:
    """Build and inject a normalized preamble into state."""
    context = _build_context(state, project_profile=project_profile)
    preamble = _render_preamble(context)
    state["session_id"] = context["session_id"]
    state["round_id"] = context["round_id"]
    state["preamble_context"] = context
    state["skill_preamble"] = preamble
    return preamble

