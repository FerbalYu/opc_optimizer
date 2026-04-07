import os
import json
import logging
import re
import time
from state import OptimizerState
from utils.llm import LLMService
from utils.file_ops import (
    read_file,
    write_to_file,
    get_project_files,
    rank_files_by_complexity,
)
from utils.methodology import PLAN_METHODOLOGY

logger = logging.getLogger("opc.plan")


def _get_llm(state, node_key: str = "model") -> "LLMService":
    """Get LLM instance from state config, with per-node model override."""
    cfg = state.get("llm_config", {}) or {}
    model = cfg.get(node_key) or cfg.get("model") or None
    timeout = cfg.get("timeout", 120)
    if model:
        return LLMService(model_name=model, timeout=timeout)
    return LLMService(timeout=timeout)


def _default_round_contract(goal: str, project_files: list[str]) -> dict:
    target_files = project_files[:3]
    return {
        "round_objective": goal,
        "current_state_assessment": "Fallback contract generated because structured planning failed.",
        "product_manager_summary": "Auto-generated fallback plan.",
        "target_files": target_files,
        "acceptance_checks": [
            "At least one concrete code change should align with the round objective."
        ],
        "expected_diff": ["Touch the intended logic in the listed target files."],
        "risk_level": "medium",
        "fallback_if_blocked": "Reduce scope to the smallest verifiable change in the first target file.",
        "impact_score": 5,
        "confidence_score": 5,
        "verification_score": 3,
        "effort_score": 3,
        "verification_first_mode": False,
    }


def _normalize_round_contract(raw: dict, project_files: list[str], goal: str) -> dict:
    project_set = set(project_files)

    def _as_text(value, default: str = "") -> str:
        if value is None:
            return default
        if isinstance(value, str):
            return value.strip() or default
        return str(value).strip() or default

    def _as_str_list(value) -> list[str]:
        if isinstance(value, list):
            items = [_as_text(item) for item in value]
        elif value is None:
            items = []
        else:
            items = [_as_text(value)]
        return [item for item in items if item]

    def _as_score(value, default: int) -> int:
        try:
            score = int(value)
        except (TypeError, ValueError):
            return default
        return max(1, min(10, score))

    contract = _default_round_contract(goal, project_files)
    contract["round_objective"] = _as_text(
        raw.get("round_objective"), contract["round_objective"]
    )
    contract["current_state_assessment"] = _as_text(
        raw.get("current_state_assessment"), contract["current_state_assessment"]
    )
    contract["product_manager_summary"] = _as_text(
        raw.get("product_manager_summary"), contract["product_manager_summary"]
    )

    target_files = []
    for rel in _as_str_list(raw.get("target_files")):
        cleaned = rel.replace("\\", "/").lstrip("./")
        if cleaned in project_set and cleaned not in target_files:
            target_files.append(cleaned)
    contract["target_files"] = target_files or contract["target_files"]

    contract["acceptance_checks"] = (
        _as_str_list(raw.get("acceptance_checks")) or contract["acceptance_checks"]
    )
    contract["expected_diff"] = (
        _as_str_list(raw.get("expected_diff")) or contract["expected_diff"]
    )
    contract["risk_level"] = _as_text(
        raw.get("risk_level"), contract["risk_level"]
    ).lower()
    if contract["risk_level"] not in {"low", "medium", "high"}:
        contract["risk_level"] = "medium"
    contract["fallback_if_blocked"] = _as_text(
        raw.get("fallback_if_blocked"), contract["fallback_if_blocked"]
    )
    contract["impact_score"] = _as_score(
        raw.get("impact_score"), contract["impact_score"]
    )
    contract["confidence_score"] = _as_score(
        raw.get("confidence_score"), contract["confidence_score"]
    )
    contract["verification_score"] = _as_score(
        raw.get("verification_score"), contract["verification_score"]
    )
    contract["effort_score"] = _as_score(
        raw.get("effort_score"), contract["effort_score"]
    )
    contract["verification_first_mode"] = bool(
        raw.get("verification_first_mode", contract["verification_first_mode"])
    )
    return contract


def _render_round_contract(contract: dict, current_round: int) -> str:
    target_files = contract.get("target_files", []) or []
    acceptance_checks = contract.get("acceptance_checks", []) or []
    expected_diff = contract.get("expected_diff", []) or []

    file_lines = (
        "\n".join(f"- {path}" for path in target_files) if target_files else "- (none)"
    )
    check_lines = (
        "\n".join(f"- {item}" for item in acceptance_checks)
        if acceptance_checks
        else "- (none)"
    )
    diff_lines = (
        "\n".join(f"- {item}" for item in expected_diff)
        if expected_diff
        else "- (none)"
    )

    return f"""# Round Contract - Round {current_round}

## Round Objective
{contract.get("round_objective", "")}

## Product Manager Summary
{contract.get("product_manager_summary", "Not provided.")}

## Current State Assessment
{contract.get("current_state_assessment", "")}

## Target Files
{file_lines}

## Acceptance Checks
{check_lines}

## Expected Diff
{diff_lines}

## Risk Level
{contract.get("risk_level", "medium")}

## Fallback If Blocked
{contract.get("fallback_if_blocked", "")}

## Task Scoring
- impact_score: {contract.get("impact_score", 5)}
- confidence_score: {contract.get("confidence_score", 5)}
- verification_score: {contract.get("verification_score", 3)}
- effort_score: {contract.get("effort_score", 3)}

## Mode Overrides
- Verification-First Mode: {contract.get("verification_first_mode", False)}
"""


def _extract_task_path(expected_diff_item: str) -> str:
    if not isinstance(expected_diff_item, str):
        return ""
    match = re.match(r"\s*(?:In\s+)?(.+?):\s*", expected_diff_item)
    if not match:
        return ""
    return match.group(1).strip().replace("\\", "/").lstrip("./")


def _build_review_tasks(contract: dict) -> list[dict]:
    tasks = []
    acceptance_checks = contract.get("acceptance_checks", []) or []
    target_files = contract.get("target_files", []) or []
    for idx, item in enumerate(contract.get("expected_diff", []) or []):
        filepath = _extract_task_path(item)
        detail = item.strip() if isinstance(item, str) else str(item)
        title = detail.split(":", 1)[1].strip() if ":" in detail else detail
        if not filepath and idx < len(target_files):
            filepath = target_files[idx]
        related_checks = [
            check
            for check in acceptance_checks
            if not filepath or filepath in str(check)
        ][:5]
        tasks.append(
            {
                "id": f"task_{idx + 1}",
                "index": idx,
                "title": title or f"Task {idx + 1}",
                "filepath": filepath,
                "detail": detail,
                "acceptance_checks": related_checks or acceptance_checks[:3],
            }
        )
    return tasks


def _filter_contract_by_selected_tasks(
    contract: dict, selected_task_ids: list[str]
) -> dict:
    selected_set = set(selected_task_ids or [])
    tasks = _build_review_tasks(contract)
    selected_tasks = [task for task in tasks if task["id"] in selected_set]
    if not selected_tasks:
        return contract

    selected_paths = []
    for task in selected_tasks:
        path = task.get("filepath", "")
        if path and path not in selected_paths:
            selected_paths.append(path)

    filtered = dict(contract)
    filtered["expected_diff"] = [task["detail"] for task in selected_tasks]
    filtered["target_files"] = selected_paths or contract.get("target_files", [])

    acceptance_checks = contract.get("acceptance_checks", []) or []
    filtered_checks = []
    for check in acceptance_checks:
        text = str(check)
        if not selected_paths or any(path in text for path in selected_paths):
            filtered_checks.append(text)
    filtered["acceptance_checks"] = filtered_checks or acceptance_checks
    return filtered


def _review_contract_with_web_ui(
    state: OptimizerState, contract: dict, current_round: int
) -> tuple[dict, str, str]:
    ui_preferences = state.get("ui_preferences", {}) or {}
    if ui_preferences.get("skip_plan_review"):
        state["consecutive_rejections"] = 0
        return contract, "approved", ""

    try:
        from ui.web_server import emit, wait_for_user_command, _clients

        if not _clients:
            state["consecutive_rejections"] = 0
            return contract, "approved", ""

        tasks = _build_review_tasks(contract)
        state["active_tasks"] = tasks
        emit(
            "task_plan_active",
            {
                "round": current_round,
                "tasks": tasks,
                "contract": contract,
                "review_required": True,
            },
        )
        emit(
            "plan_review_required",
            {
                "round": current_round,
                "tasks": tasks,
                "contract": contract,
            },
        )

        while True:
            cmd = wait_for_user_command(timeout=3600)
            if not cmd:
                logger.warning("Plan review timed out; approving current task batch")
                state["consecutive_rejections"] = 0
                return contract, "approved", "timed out"

            action = cmd.get("action")
            if action == "approve_plan":
                selected_ids = cmd.get("approved_task_ids", []) or []
                if not selected_ids:
                    emit(
                        "plan_review_result",
                        {"status": "needs_replan", "reason": "no_tasks_selected"},
                    )
                    state["consecutive_rejections"] = (
                        state.get("consecutive_rejections", 0) + 1
                    )
                    return contract, "replan", cmd.get("note", "No tasks selected")
                approved_contract = _filter_contract_by_selected_tasks(
                    contract, selected_ids
                )
                state["active_tasks"] = _build_review_tasks(approved_contract)
                # Successful approval resets the rejection counter
                state["consecutive_rejections"] = 0
                emit(
                    "plan_review_result",
                    {
                        "status": "approved",
                        "tasks": state["active_tasks"],
                        "contract": approved_contract,
                    },
                )
                return approved_contract, "approved", cmd.get("note", "")
            if action == "replan_plan":
                rejections = state.get("consecutive_rejections", 0) + 1
                state["consecutive_rejections"] = rejections

                # ── Opt-5: Circuit Breaker ────────────────────────────
                if rejections >= 3:
                    logger.warning(
                        f"Circuit breaker triggered after {rejections} consecutive plan rejections. "
                        "Halting the current round."
                    )
                    state["circuit_breaker_triggered"] = True
                    emit(
                        "circuit_breaker",
                        {
                            "round": current_round,
                            "consecutive_rejections": rejections,
                            "message": (
                                f"Circuit breaker triggered after {rejections} consecutive plan rejections. "
                                "This task appears to exceed the current AI capability. "
                                "Please simplify the goal or rephrase the task."
                            ),
                        },
                    )
                    return (
                        contract,
                        "circuit_break",
                        f"{rejections} consecutive rejections",
                    )

                emit(
                    "plan_review_result",
                    {
                        "status": "replan",
                        "reason": cmd.get("note", "User rejected current task batch"),
                        "consecutive_rejections": rejections,
                    },
                )
                return (
                    contract,
                    "replan",
                    cmd.get("note", "User rejected current task batch"),
                )
    except Exception as e:
        logger.warning(f"Web UI plan review failed, auto-approving: {e}")
    state["consecutive_rejections"] = 0
    return contract, "approved", ""


def plan_node(state: OptimizerState) -> OptimizerState:
    logger.info("--- 🔍 PLAN PHASE ---")

    # Record round start time for metrics tracking and timeout enforcement
    state["round_start_time"] = time.time()

    goal = state["optimization_goal"]
    project_path = state["project_path"]
    current_round = state.get("current_round", 1)
    logger.info(f"Round {current_round} | Goal: {goal}")

    llm = _get_llm(state, "plan_model")

    # ── Smart Project Profile (v2.10.0) ─────────────────────────
    profile = None
    profile_hints = ""
    try:
        from utils.project_profile import load_project_profile

        profile = load_project_profile(project_path)
        hints = profile.get("optimization_hints", [])
        if hints:
            profile_hints = "\n## Project-Specific Optimization Hints:\n"
            profile_hints += "\n".join(f"- {h}" for h in hints)
            logger.info(
                f"Loaded {len(hints)} optimization hints for {profile.get('type', 'unknown')}"
            )
    except Exception as e:
        logger.warning(f"Project profile loading failed: {e}")

    # ── Unified skill preamble (Phase 2 / P2-2) ─────────────────
    preamble_block = ""
    try:
        from utils.skill_preamble import inject_skill_preamble

        preamble_text = inject_skill_preamble(state, project_profile=profile)
        preamble_block = preamble_text + "\n"
    except Exception as e:
        logger.warning(f"Preamble injection failed in plan node: {e}")

    # ── SKILL 优化策略 (v2.12.0) ─────────────────────────────
    skill_content = ""
    try:
        from utils.skill_loader import load_skills

        skill_content = load_skills(project_path, profile)
        if skill_content:
            logger.info(f"Loaded SKILL content ({len(skill_content)} chars)")
    except Exception as e:
        logger.warning(f"SKILL loading failed: {e}")

    # Build project file tree for context (sorted by complexity — v2.2.0)
    project_files = rank_files_by_complexity(
        get_project_files(project_path, profile=profile)
    )
    project_rel_files = [
        os.path.relpath(f, project_path).replace("\\", "/") for f in project_files
    ]
    file_tree = "\n".join(rel_path for rel_path in project_rel_files)

    # ── Multi-round Memory (v2.2.0 + v2.7.0 condensation) ─────────
    history_context = ""
    condensed = state.get("condensed_history", "")
    if condensed:
        # Use condensed history (v2.7.0) — much shorter, keeps recent detail
        history_context = (
            "\n## Previous Round History (DO NOT repeat these changes):\n" + condensed
        )
    else:
        # Fallback: raw round_history (pre-condensation or first round)
        round_history = state.get("round_history", []) or []
        if round_history:
            history_context = (
                "\n## Previous Round History (DO NOT repeat these changes):\n"
            )
            for rh in round_history[-5:]:
                history_context += f"\n### Round {rh.get('round', '?')}\n"
                changed = rh.get("files_changed", [])
                if changed:
                    history_context += f"- Files changed: {', '.join(changed)}\n"
                summary = rh.get("summary", "N/A")
                if summary:
                    history_context += f"- Changes: {summary[:200]}\n"

    # ── Smart Context via Code Graph (v2.5.0) ────────────────────
    # Use symbol summaries instead of full file content → ~50% less tokens
    file_previews = ""
    try:
        from utils.code_graph import build_project_index

        graph = build_project_index(project_path)
        file_previews = graph.get_project_summary()
        logger.info(f"Using code graph: {len(graph.symbols)} symbols indexed")

        # Supplement signatures with full content of the top files
        # so the plan LLM can reference actual code, not just signatures
        if current_round == 1:
            top_files = list(graph.file_symbols.keys())[:3]
        else:
            prev_history = state.get("round_history", [])
            if prev_history and isinstance(prev_history[-1], dict):
                top_files = prev_history[-1].get("files_changed", [])[:3]
            else:
                top_files = []

        for rel in top_files:
            abs_path = os.path.join(project_path, rel)
            if os.path.exists(abs_path):
                content = read_file(abs_path)
                if content:
                    if len(content) > 4000:
                        content = content[:4000] + "\n... (truncated)"
                    file_previews += (
                        f"\n\n### {rel} (full content)\n```\n{content}\n```\n"
                    )
    except Exception as e:
        logger.warning(f"Code graph failed, falling back to file reading: {e}")
        # Fallback: read key files (limit to first ~80 lines each, max 10 files)
        for fp in project_files[:10]:
            rel_path = os.path.relpath(fp, project_path).replace("\\", "/")
            content = read_file(fp)
            if content:
                lines = content.splitlines()
                if len(lines) > 80:
                    preview = "\n".join(lines[:80]) + "\n... (truncated)"
                else:
                    preview = content
                file_previews += f"\n### {rel_path}\n```\n{preview}\n```\n"

    # Token budget guard (Step 25 Efficiency Upgrade)
    budget = max(8000, min(16000, llm.max_context_tokens // 4))
    file_previews = LLMService.truncate_to_budget(
        file_previews, budget, label="plan file_previews"
    )

    candidate_paths_text = (
        "\n".join(f"- {path}" for path in project_rel_files[:15])
        or "- (no files found)"
    )

    review_feedback = ""

    # Check if we have previous suggestions
    if state.get("suggestions"):
        logger.info("Reading previous suggestions to formulate plan...")
        base_prompt = f"""You are the Planning Agent for a code optimization workflow.
Target Project: {project_path}
Optimization Goal: {goal}
Current Round: {current_round}
{preamble_block}

Project File Structure:
{file_tree}

Key File Contents:
{file_previews}
{history_context}
{profile_hints}
{skill_content}

Previous Round Suggestions:
{state["suggestions"]}

Based strictly on the suggestions above and the ACTUAL project files, create a structured round contract.
The contract must reference real file paths and real code structures.
IMPORTANT: Review the Previous Round History above. Do NOT propose changes that were already made in previous rounds.
Return JSON with exactly these fields:
- round_objective: string
- current_state_assessment: string
- product_manager_summary: string
- target_files: string[]
- acceptance_checks: string[]
- expected_diff: string[]
- risk_level: "low" | "medium" | "high"
- fallback_if_blocked: string
- impact_score: integer 1-10
- confidence_score: integer 1-10
- verification_score: integer 1-10
- effort_score: integer 1-10
- verification_first_mode: boolean
Rules:
- Focus on one primary task for this round
- target_files must contain 1-3 real relative file paths from this allowlist
- acceptance_checks must be machine-checkable when possible
- expected_diff must describe concrete code changes, not vague intent
- product_manager_summary MUST explain the objective and business value/UX improvement of these changes in plain, non-technical language tailored for a Product Manager. Do not use code terminology.
- VERIFICATION-FIRST MODE: If risk_level is 'high' AND the target code lacks existing tests/verification, you MUST set verification_first_mode to true. When true, your expected_diff must ONLY propose adding tests, assertions, or dry-run scaffolding. Do NOT propose rewriting the actual algorithm yet.

Allowed target files:
{candidate_paths_text}
{PLAN_METHODOLOGY}
"""
    else:
        logger.info("Initial round: Performing full project scan and generating plan.")
        base_prompt = f"""You are the Planning Agent for a code optimization workflow.
Target Project: {project_path}
Optimization Goal: {goal}
Current Round: {current_round} (Initial)
{preamble_block}

Project File Structure (sorted by complexity, most complex first):
{file_tree}

Key File Contents:
{file_previews}
{history_context}
{profile_hints}
{skill_content}

This is the first round. Analyze the ACTUAL project code above and generate a structured round contract.
Your contract must reference real files and real code patterns you see.
Return JSON with exactly these fields:
- round_objective: string
- current_state_assessment: string
- product_manager_summary: string
- target_files: string[]
- acceptance_checks: string[]
- expected_diff: string[]
- risk_level: "low" | "medium" | "high"
- fallback_if_blocked: string
- impact_score: integer 1-10
- confidence_score: integer 1-10
- verification_score: integer 1-10
- effort_score: integer 1-10
- verification_first_mode: boolean
Rules:
- Focus on one primary task for this round
- target_files must contain 1-3 real relative file paths from this allowlist
- acceptance_checks must be machine-checkable when possible
- expected_diff must describe concrete code changes, not vague intent
- product_manager_summary MUST explain the objective and business value/UX improvement of these changes in plain, non-technical language tailored for a Product Manager. Do not use code terminology.
- VERIFICATION-FIRST MODE: If risk_level is 'high' AND the target code lacks existing tests/verification, you MUST set verification_first_mode to true. When true, your expected_diff must ONLY propose adding tests, assertions, or dry-run scaffolding. Do NOT propose rewriting the actual algorithm yet.

Allowed target files:
{candidate_paths_text}
{PLAN_METHODOLOGY}
"""

    MAX_ATTEMPTS = 5
    contract = None
    for attempt in range(MAX_ATTEMPTS):
        prompt = base_prompt
        if review_feedback:
            prompt += f"""

Web UI feedback on the previous task batch:
{review_feedback}

Generate a different batch that better matches the feedback. Do not repeat the previously rejected task list.
"""
        try:
            raw_contract = llm.generate_json(
                [
                    {
                        "role": "system",
                        "content": f"You are the Planning Agent for a code optimization workflow. Generate a strict JSON round contract based only on real project code and prior round evidence. NO EXPLANATIONS REQUIRED. Output pure JSON.\n{PLAN_METHODOLOGY}",
                    },
                    {"role": "user", "content": prompt},
                ]
            )
            contract = _normalize_round_contract(raw_contract, project_rel_files, goal)
        except Exception as e:
            logger.warning(
                f"Structured plan generation failed (attempt {attempt + 1}/{MAX_ATTEMPTS}): {e}"
            )
            if attempt < MAX_ATTEMPTS - 1:
                review_feedback = f"SYSTEM ERROR: Your previous response failed to parse as valid JSON. Error detail: {e}\n\n### 🔴 CRITICAL CORRECTION REQUIRED\n1. NO EXPLANATIONS: Do not write analytic essays.\n2. STRICT JSON: You MUST output a strictly valid JSON object."
                logger.info(
                    "Triggering self-correction retry due to JSON parse failure (Laziness trap)."
                )
                continue
            else:
                logger.error(
                    "All attempts to generate structured JSON failed. Falling back to default contract."
                )
                contract = _default_round_contract(goal, project_rel_files)

        contract, review_status, review_note = _review_contract_with_web_ui(
            state, contract, current_round
        )
        if review_status == "approved":
            break
        if review_status == "circuit_break":
            logger.warning("Plan circuit breaker activated. Aborting round.")
            state["should_stop"] = (
                True  # abort this round; interact node will offer new task
            )
            state["code_diff"] = (
                "Circuit breaker: too many consecutive plan rejections. Round aborted."
            )
            state["consecutive_rejections"] = 0  # reset so next task starts fresh
            return state

        if attempt == MAX_ATTEMPTS - 1:
            logger.warning(
                "Max plan replan attempts reached. Aborting round due to user rejection."
            )
            state["should_stop"] = True
            state["code_diff"] = "User continuously rejected the plan. Round aborted."
            return state

        review_feedback = (
            review_note
            or "User rejected the previous task batch and requested a different set of tasks."
        )

    plan = _render_round_contract(contract, current_round)

    # Write plan to external workspace (Opt-6)
    try:
        from utils.workspace import workspace_path

        plan_path = workspace_path(
            project_path, "logs", f"round_{current_round}_plan.md"
        )
        contract_path = workspace_path(
            project_path, "logs", f"round_{current_round}_contract.json"
        )
    except Exception:
        plan_path = os.path.join(project_path, ".opclog", "plan.md")
        contract_path = os.path.join(project_path, ".opclog", "round_contract.json")
    write_to_file(plan_path, plan)
    write_to_file(contract_path, json.dumps(contract, indent=2, ensure_ascii=False))

    # Backward-compatible mirror for legacy readers/tests under project/.opclog.
    legacy_plan_path = os.path.join(project_path, ".opclog", "plan.md")
    legacy_contract_path = os.path.join(project_path, ".opclog", "round_contract.json")
    if os.path.abspath(plan_path) != os.path.abspath(legacy_plan_path):
        write_to_file(legacy_plan_path, plan)
    if os.path.abspath(contract_path) != os.path.abspath(legacy_contract_path):
        write_to_file(legacy_contract_path, json.dumps(contract, indent=2, ensure_ascii=False))

    state["current_plan"] = plan
    state["round_contract"] = contract
    state["active_tasks"] = _build_review_tasks(contract)
    try:
        from ui.web_server import emit

        emit(
            "task_plan_active",
            {
                "round": current_round,
                "tasks": state["active_tasks"],
                "contract": contract,
                "review_required": not (
                    (state.get("ui_preferences", {}) or {}).get("skip_plan_review")
                ),
            },
        )
    except Exception:
        pass
    logger.info(f"Round contract generated and saved to {plan_path}")
    return state
