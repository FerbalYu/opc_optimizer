import os
import json
import re
import shutil
import logging
import tempfile
from contextlib import contextmanager
from state import OptimizerState
from utils.llm import LLMService
from utils.file_ops import read_file, write_to_file, append_to_file, get_project_files
from utils.code_reviewer import CodeReviewer
from utils.methodology import EXECUTE_METHODOLOGY
from utils.constants import MAX_FILES, MAX_FILE_CONTENT_LENGTH

logger = logging.getLogger("opc.execute")


@contextmanager
def _sandbox_file(filepath: str):
    """安全创建临时沙箱文件，自动清理。

    Yields:
        str: 沙箱文件的绝对路径
    """
    sandbox_dir = tempfile.mkdtemp(prefix="opc_sandbox_")
    sandbox_file = os.path.join(sandbox_dir, os.path.basename(filepath))
    try:
        yield sandbox_file
    finally:
        try:
            shutil.rmtree(sandbox_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Failed to cleanup sandbox dir {sandbox_dir}: {e}")


def _clean_llm_response(text: str) -> str:
    """Strip model-specific internal tokens from LLM output.

    MiniMax models may leak <think>...</think> blocks and
    <minimax:tool_call> markers into their responses.
    """
    # Remove <think>...</think> blocks (thinking traces)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Remove orphaned </think> tags
    text = re.sub(r"</think>", "", text)
    # Remove <minimax:tool_call> blocks
    text = re.sub(
        r"<minimax:tool_call>.*?</minimax:tool_call>", "", text, flags=re.DOTALL
    )
    # Remove orphaned <minimax:tool_call> tags
    text = re.sub(r"<minimax:tool_call>", "", text)
    return text.strip()


def _needs_filepath_retry(raw_response: str, modifications: list) -> bool:
    """Detect placeholder-heavy outputs that deserve one stricter retry."""
    if modifications:
        return False

    lowered = (raw_response or "").lower()
    if "<<<<<<< search" not in lowered:
        return False

    retry_markers = (
        "<filepath>",
        "</think>",
        "<minimax:tool_call>",
        '"filepath": "<filepath>"',
        "'filepath': '<filepath>'",
    )
    return any(marker in lowered for marker in retry_markers)


def _get_llm(state, node_key: str = "model") -> "LLMService":
    """Get LLM instance from state config, with per-node model override."""
    cfg = state.get("llm_config", {}) or {}
    model = cfg.get(node_key) or cfg.get("model") or None
    timeout = cfg.get("timeout", 120)
    if model:
        return LLMService(model_name=model, timeout=timeout)
    return LLMService(timeout=timeout)


def _normalize_contract_paths(round_contract: dict) -> list[str]:
    """Normalize round-contract target paths into safe relative project paths."""
    if not isinstance(round_contract, dict):
        return []

    normalized = []
    seen = set()
    for path in round_contract.get("target_files", []) or []:
        if not isinstance(path, str):
            continue
        cleaned = path.replace("\\", "/").strip().lstrip("./")
        if not cleaned or cleaned in seen:
            continue
        norm = os.path.normpath(cleaned).replace("\\", "/")
        if norm.startswith("..") or os.path.isabs(norm):
            continue
        normalized.append(norm)
        seen.add(norm)
    return normalized


def _get_execute_allowed_paths(
    round_contract: dict | None, discovered_targets: list[str]
) -> list[str]:
    """Resolve which target files are editable this round.

    Files explicitly marked as "No changes needed" in expected_diff stay readable
    for context, but are removed from the execute allowlist.
    """
    contract_paths = _normalize_contract_paths(round_contract or {})
    allowed = contract_paths or list(discovered_targets)
    if not round_contract:
        return allowed

    readonly = set()
    for item in round_contract.get("expected_diff", []) or []:
        if not isinstance(item, str):
            continue
        match = re.match(r"\s*In\s+(.+?):\s*(.+)", item, flags=re.IGNORECASE)
        if not match:
            continue
        path = match.group(1).strip().replace("\\", "/").lstrip("./")
        detail = match.group(2).strip().lower()
        if "no changes needed" in detail:
            readonly.add(os.path.normpath(path).replace("\\", "/"))

    filtered = [path for path in allowed if path not in readonly]
    return filtered if filtered else allowed


def _is_safe_path(filepath: str, project_path: str) -> bool:
    """严格验证路径安全性，防止符号链接和路径遍历攻击。

    Args:
        filepath: 相对于project_path的路径
        project_path: 项目根目录

    Returns:
        True if path is safe (resolves within project), False otherwise
    """
    try:
        from pathlib import Path

        project = Path(project_path).resolve()
        target = (Path(project_path) / filepath).resolve()
        return str(target).startswith(str(project))
    except Exception:
        return False


def _read_target_files(
    project_path: str, plan: str, round_contract: dict | None = None
) -> dict:
    """Read files mentioned in the plan. Falls back to scanning project files."""
    all_files = get_project_files(project_path)

    # Build a map of basename -> full path for quick lookup
    file_map = {}
    for fp in all_files:
        rel = os.path.relpath(fp, project_path).replace("\\", "/")
        file_map[rel] = fp

    contract_targets = {}
    for rel_path in _normalize_contract_paths(round_contract or {}):
        abs_path = file_map.get(rel_path)
        if abs_path:
            contract_targets[rel_path] = abs_path

    if contract_targets:
        targets = contract_targets
    else:
        # Try to find files mentioned in the plan text
        mentioned = {}
        for rel_path, abs_path in file_map.items():
            if rel_path in plan or os.path.basename(abs_path) in plan:
                mentioned[rel_path] = abs_path

        # If nothing matched, include all project files (capped)
        targets = mentioned if mentioned else file_map

        # Limit total files to prevent prompt explosion
        if len(targets) > MAX_FILES:
            targets = dict(list(targets.items())[:MAX_FILES])

    contents = {}
    for rel_path, abs_path in targets.items():
        try:
            content = read_file(abs_path)
            if len(content) > MAX_FILE_CONTENT_LENGTH:
                content = content[:MAX_FILE_CONTENT_LENGTH] + "\n... (truncated)"
            contents[rel_path] = content
        except Exception:
            contents[rel_path] = "(failed to read)"

    return contents


def _build_smart_context(
    project_path: str, plan: str, round_contract: dict | None = None
) -> str:
    """Build smart context using code graph (v2.5.0).

    Target files → full content. Dependencies → signatures only.
    Falls back to _read_target_files on error.
    """
    try:
        from utils.code_graph import build_project_index

        graph = build_project_index(project_path)

        # Prefer structured contract targets, then fall back to plan text.
        target_files = [
            rel_path
            for rel_path in _normalize_contract_paths(round_contract or {})
            if rel_path in graph.file_symbols
        ]
        if not target_files:
            for rel_path in graph.file_symbols.keys():
                if rel_path in plan or os.path.basename(rel_path) in plan:
                    target_files.append(rel_path)

        if not target_files:
            # Fallback: use all indexed files as targets
            target_files = list(graph.file_symbols.keys())[:5]

        context = graph.get_smart_context(target_files, plan)
        if context:
            logger.info(
                f"Smart context: {len(target_files)} targets, {len(graph.symbols)} symbols"
            )
            return context
    except Exception as e:
        logger.warning(f"Smart context failed, using legacy: {e}")

    # Legacy fallback
    file_contents = _read_target_files(
        project_path, plan, round_contract=round_contract
    )
    parts = []
    for rel_path, content in file_contents.items():
        parts.append(f"\n### {rel_path}\n```\n{content}\n```\n")
    return "".join(parts)


def _filter_modifications_to_contract(
    modifications: list,
    round_contract: dict | None,
    allowed_paths: list[str] | None = None,
) -> tuple[list, list]:
    """Keep only modifications allowed by the round contract target files."""
    allowed_set = set(allowed_paths or _normalize_contract_paths(round_contract or {}))
    if not allowed_set:
        return modifications, []

    kept = []
    rejected = []
    for mod in modifications:
        raw_path = mod.get("filepath", "")
        cleaned = os.path.normpath(
            str(raw_path).replace("\\", "/").strip().lstrip("./")
        ).replace("\\", "/")
        if cleaned in allowed_set:
            mod["filepath"] = cleaned
            kept.append(mod)
        else:
            rejected.append(
                f"Filtered out-of-contract modification for {raw_path or 'unknown_file'} "
                f"(allowed: {', '.join(sorted(allowed_set))})"
            )
    return kept, rejected


def _build_doc_context(project_path: str, plan: str) -> str:
    """Build optional framework/library docs grounding via Context7."""
    try:
        from utils.context7_client import collect_relevant_docs
        from utils.project_profile import load_project_profile

        profile = load_project_profile(project_path)
        docs = collect_relevant_docs(project_path, plan, profile=profile)
        if docs:
            logger.info(f"Loaded Context7 docs grounding ({len(docs)} chars)")
        return docs
    except Exception as e:
        logger.warning(f"Context7 docs grounding failed: {e}")
        return ""


# ── Formatter cache (v2.8.0) ─────────────────────────────────────
_formatter_cache: dict = {}


def _get_formatter(project_path: str) -> dict | None:
    """Get (and cache) the project formatter config."""
    if project_path in _formatter_cache:
        return _formatter_cache[project_path]

    from utils.formatter import detect_formatter, parse_formatter_spec

    # Check for CLI/env override
    explicit = os.environ.get("OPC_FORMATTER", "")
    if explicit.lower() == "none":
        _formatter_cache[project_path] = None
        return None
    if explicit:
        fmt = parse_formatter_spec(explicit)
        _formatter_cache[project_path] = fmt
        if fmt:
            logger.info(f"Using explicit formatter: {fmt['name']}")
        return fmt

    # Auto-detect
    fmt = detect_formatter(project_path)
    _formatter_cache[project_path] = fmt
    return fmt


# Shared reviewer instance
_reviewer = CodeReviewer()


def _apply_modification(
    project_path: str, mod: dict, dry_run: bool = False, auto_mode: bool = False
) -> str:
    """Apply a single file modification via temp-dir sandbox + fuzzy matching.

    v2.4.0: Uses fuzzy matching when exact match fails. Supports diff review
    via WebSocket (or CLI fallback) for uncertain matches.
    """
    from utils.diff_parser import fuzzy_find_and_replace, generate_diff_preview

    filepath = mod.get("filepath", "")
    old_snippet = mod.get("old_content_snippet", "")
    new_content = mod.get("new_content", "")
    reason = mod.get("reason", "No reason provided")

    # Path traversal protection - 使用严格路径验证
    norm_path = os.path.normpath(filepath)
    if norm_path.startswith("..") or os.path.isabs(filepath):
        return f"BLOCKED {filepath}: path traversal or absolute path rejected"

    # 增强验证：使用pathlib防止符号链接绕过
    abs_path = os.path.join(project_path, filepath)
    if not _is_safe_path(abs_path, project_path):
        return f"BLOCKED {filepath}: resolved path escapes project directory"

    if not os.path.exists(abs_path):
        return f"SKIP {filepath}: file not found"

    if not old_snippet:
        return f"SKIP {filepath}: no old_content_snippet provided"

    original = read_file(abs_path)

    # ── Fuzzy matching (v2.4.0) ──────────────────────────────────
    patched, similarity, status = fuzzy_find_and_replace(
        original, old_snippet, new_content
    )

    if status == "rejected":
        return f"SKIP {filepath}: no matching code found (similarity={similarity:.0%})"

    # Opt-2: ambiguous match — two equally similar regions found, refuse auto-apply
    if status == "ambiguous":
        logger.warning(
            f"Ambiguous fuzzy match for {filepath}: pushing for human review."
        )
        if patched and not auto_mode:
            diff_preview = generate_diff_preview(filepath, original, patched)
            approved = _request_diff_review(
                filepath, diff_preview, similarity, auto_mode
            )
            if approved:
                # User confirmed which match to apply
                pass
            else:
                return f"SKIP {filepath}: ambiguous fuzzy match — {similarity:.0%} similarity (human rejected)"
        elif auto_mode:
            # In auto_mode, skip ambiguous matches to avoid mis-applying
            return f"SKIP {filepath}: ambiguous fuzzy match rejected in auto_mode (similarity={similarity:.0%})"
        else:
            return (
                f"SKIP {filepath}: ambiguous fuzzy match (similarity={similarity:.0%})"
            )

    if status == "needs_confirm" and not auto_mode:
        # Ask user for confirmation via WebSocket or CLI
        diff_preview = generate_diff_preview(filepath, original, patched)
        approved = _request_diff_review(filepath, diff_preview, similarity, auto_mode)
        if not approved:
            return f"SKIP {filepath}: user rejected fuzzy match (similarity={similarity:.0%})"

    if status == "auto_fuzzy":
        logger.warning(f"  ⚠️ Fuzzy match for {filepath} (similarity={similarity:.0%})")

    # Review LLM-generated code for suspicious patterns
    is_safe, issues = _reviewer.review(new_content)
    if not is_safe:
        issue_text = "; ".join(issues)
        return f"BLOCKED {filepath}: code review rejected — {issue_text}"
    if issues:
        for issue in issues:
            logger.warning(f"  Code review [{filepath}]: {issue}")

    if dry_run:
        return f"DRY-RUN {filepath}: would modify — {reason}"

    # ── Sandbox verification ──
    with _sandbox_file(filepath) as sandbox_file:
        with open(sandbox_file, "w", encoding="utf-8") as f:
            f.write(patched)

        # Verify: if Python file, compile to catch syntax errors
        if filepath.endswith(".py"):
            try:
                compile(patched, filepath, "exec")
            except SyntaxError as e:
                return f"BLOCKED {filepath}: sandbox compilation failed — {e}"

        # Verification passed — apply to real project
        backup_path = abs_path + ".bak"
        shutil.copy2(abs_path, backup_path)
        shutil.copy2(sandbox_file, abs_path)

        # ── Post-write formatter (v2.8.0) ────────────────────────
        format_info = ""
        try:
            from utils.formatter import format_file

            _fmt = _get_formatter(project_path)
            if _fmt:
                ok, msg = format_file(_fmt, abs_path, project_path)
                if ok and "Formatted" in msg:
                    format_info = " [formatted]"
                    logger.info(f"  🧹 {msg}")
        except Exception:
            pass  # Formatting should never block modifications

        match_info = f" [fuzzy={similarity:.0%}]" if status != "exact" else ""
        return f"MODIFIED {filepath}: {reason}{match_info}{format_info}"


def _request_diff_review(
    filepath: str, diff_preview: str, similarity: float, auto_mode: bool
) -> bool:
    """Request user review for a fuzzy-matched diff.

    Tries WebSocket first, falls back to CLI.
    Returns True if approved, False if rejected.
    """
    try:
        from ui.web_server import emit, wait_for_user_command, _clients

        if _clients:
            # Send diff for review via WebSocket
            emit(
                "diff_review",
                {
                    "filepath": filepath,
                    "diff": diff_preview,
                    "similarity": round(similarity, 4),
                },
            )
            # Wait for response (60s timeout)
            cmd = wait_for_user_command(timeout=60)
            if cmd and cmd.get("action") == "accept_diff":
                return True
            elif cmd and cmd.get("action") == "reject_diff":
                return False
            # Timeout: auto_mode → accept, otherwise reject
            return auto_mode
    except Exception:
        pass

    # CLI fallback
    logger.info(f"\n{'=' * 60}")
    logger.info(f"📝 Fuzzy match for: {filepath} (similarity={similarity:.0%})")
    logger.info(f"{'=' * 60}")
    for line in diff_preview.split("\n")[:20]:
        logger.info(f"  {line}")
    if len(diff_preview.split("\n")) > 20:
        logger.info(f"  ... ({len(diff_preview.split(chr(10))) - 20} more lines)")
    logger.info(f"{'=' * 60}")

    if auto_mode:
        logger.info("Auto-mode: accepting fuzzy match")
        return True

    try:
        answer = input(f"Accept this change? [y/N]: ").strip().lower()
        return answer in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def execute_node(state: OptimizerState) -> OptimizerState:
    logger.info("--- ⚡ EXECUTE PHASE ---")
    current_plan = state.get("current_plan", "")
    project_path = state["project_path"]
    current_round = state.get("current_round", 1)
    dry_run = state.get("dry_run", False)
    auto_mode = state.get("auto_mode", False)
    round_contract = state.get("round_contract", {}) or {}

    if not current_plan:
        logger.warning("No plan found. Skipping execution.")
        state["code_diff"] = "No changes executed (missing plan)."
        return state

    if dry_run:
        logger.info("🏜️ DRY-RUN mode — changes will be simulated only")

    logger.info("Spawning Execution Sub-Agent to process plan...")

    llm = _get_llm(state, "execute_model")

    # ── Smart Context (v2.5.0) ─────────────────────────────────────
    logger.info("Building smart context...")
    target_files = list(
        _read_target_files(
            project_path, current_plan, round_contract=round_contract
        ).keys()
    )
    execute_allowed_paths = _get_execute_allowed_paths(round_contract, target_files)
    files_context = _build_smart_context(
        project_path, current_plan, round_contract=round_contract
    )
    docs_context = _build_doc_context(project_path, current_plan)

    preamble_block = ""
    try:
        from utils.skill_preamble import inject_skill_preamble
        from utils.project_profile import load_project_profile

        execute_profile = load_project_profile(project_path)
        preamble_text = inject_skill_preamble(state, project_profile=execute_profile)
        preamble_block = preamble_text + "\n"
    except Exception as e:
        logger.warning(f"Preamble injection failed in execute node: {e}")

    # Token budget guard (Step 25 Efficiency Upgrade)
    budget = max(12000, min(24000, llm.max_context_tokens // 2))
    files_context = LLMService.truncate_to_budget(
        files_context, budget, label="execute files_context"
    )
    if docs_context:
        docs_budget = max(1200, min(4000, budget // 3))
        docs_context = LLMService.truncate_to_budget(
            docs_context, docs_budget, label="execute docs_context"
        )

    allowed_paths_text = (
        "\n".join(f"- {path}" for path in execute_allowed_paths[:15])
        or "- (no editable files discovered)"
    )
    contract_json = (
        json.dumps(round_contract, indent=2, ensure_ascii=False)
        if round_contract
        else "{}"
    )
    acceptance_checks = round_contract.get("acceptance_checks", []) or []
    expected_diff = round_contract.get("expected_diff", []) or []
    acceptance_text = "\n".join(f"- {item}" for item in acceptance_checks) or "- (none)"
    expected_diff_text = "\n".join(f"- {item}" for item in expected_diff) or "- (none)"
    readonly_paths = sorted(set(target_files) - set(execute_allowed_paths))
    readonly_text = "\n".join(f"- {path}" for path in readonly_paths) or "- (none)"

    # ── Opt-4: Arch context injection ─────────────────────────────
    # Injected at the very top of the prompt so the model sees the global
    # architecture BEFORE any file-level context.
    arch_hint = ""
    try:
        from utils.arch_context import load_arch_context

        arch_hint = load_arch_context(project_path)
    except Exception as _arch_exc:
        logger.debug(f"Arch context load failed (non-fatal): {_arch_exc}")

    arch_preamble = (arch_hint.strip() + "\n\n") if arch_hint.strip() else ""

    # v2.4.0: SEARCH/REPLACE prompt format
    prompt = f"""You are the Execution Agent for a code optimization workflow.
{preamble_block}{arch_preamble}Target Project: {project_path}

Here is the current optimization plan:
{current_plan}

Structured round contract:
```json
{contract_json}
```

Acceptance checks for this round:
{acceptance_text}

Expected diff for this round:
{expected_diff_text}

Read-only files for this round (context only, do not edit):
{readonly_text}

Here are the actual file contents from the project:
{files_context}
"""

    if docs_context:
        prompt += f"""

Relevant framework/library docs grounding:
{docs_context}
"""

    if round_contract.get("verification_first_mode"):
        prompt += """
🚨 VERIFICATION-FIRST MODE ENFORCED 🚨
Because this is a high-risk change without existing tests, your ONLY allowable changes in this round are adding tests, assertions, or logging to verify the CURRENT behavior.
DO NOT modify the core business logic yet.
"""

    prompt += f"""

Based on this plan and the ACTUAL file contents, output SEARCH/REPLACE blocks for each change.

Format for each change:

pages/index/index.js
<<<<<<< SEARCH
<exact lines from current file to replace>
=======
<new replacement lines>
>>>>>>> REPLACE

RULES:
- The filepath line must be a REAL relative project path from the allowed list below
- NEVER output placeholders like <filepath>, file.py, filename, path, or XML/tool tags
- The SEARCH block must be an EXACT substring copy of the current file (whitespace matters)
- One SEARCH/REPLACE block per change. Multiple blocks allowed for the same file.
- Only propose changes you are confident about based on the real code
- Copy enough context lines to make the match unambiguous
- Stay inside the round contract. If a useful change would require files outside the contract, do not propose it in this round.
- Each proposed change should help satisfy at least one acceptance check and match the expected diff.

Allowed filepaths for this task:
{allowed_paths_text}

{EXECUTE_METHODOLOGY}

### 🔴 CRITICAL RULES FOR CODE GENERATION
1. **NO EXPLANATIONS REQUIRED**: Do not write essays or analyze theory. Your ONLY job is to write the code solution.
2. **ACTION ORIENTED**: Every response must contain directly actionable SEARCH/REPLACE code blocks.
3. **DO NOT SAY, DO IT**: If the change is simple (like an errorCount increment), just output the SEARCH/REPLACE block for it immediately.
"""

    try:
        # Use generate() for raw text (SEARCH/REPLACE) instead of generate_json()
        from utils.diff_parser import parse_llm_output

        raw_response = llm.generate(
            [
                {
                    "role": "system",
                    "content": f"You are the Execution Agent. Propose precise file modifications using SEARCH/REPLACE blocks. If you cannot use that format, fall back to JSON with 'modifications' array containing filepath/old_content_snippet/new_content/reason.\n{EXECUTE_METHODOLOGY}",
                },
                {"role": "user", "content": prompt},
            ]
        )

        # Clean model-specific internal tokens before parsing
        raw_response = _clean_llm_response(raw_response)

        modifications = parse_llm_output(raw_response)
        filtered_errors = []

        # Detect placeholder errors
        needs_retry = _needs_filepath_retry(raw_response, modifications)
        retry_reason = "placeholder filepath"

        # Detect "Laziness" / "光说不练" (Analysis without any executable code blocks)
        is_lazy = False
        if not modifications and not needs_retry:
            if "NO_CHANGES" not in raw_response:
                needs_retry = True
                is_lazy = True
                retry_reason = "laziness (analysis without code)"

        if needs_retry:
            logger.warning(
                f"Detected {retry_reason} output; triggering self-correction retry"
            )

            if is_lazy:
                retry_prompt = (
                    prompt
                    + """

### 🔴 CRITICAL CORRECTION REQUIRED
You provided an explanation but NO executable code modifications!
1. **NO EXPLANATIONS REQUIRED**: Stop analyzing the theory.
2. **ACTION ORIENTED**: You must output valid SEARCH/REPLACE blocks.
If you believe no changes are needed, return exactly: NO_CHANGES
"""
                )
            else:
                retry_prompt = (
                    prompt
                    + """

Your previous answer used invalid placeholder or tool-style filepaths.
Retry now and output ONLY valid SEARCH/REPLACE blocks.
Every block must start with one of the exact relative paths from the allowed list.
If no safe change is possible, return exactly: NO_CHANGES
"""
                )
            raw_response = llm.generate(
                [
                    {
                        "role": "system",
                        "content": f"You are the Execution Agent. Output only valid SEARCH/REPLACE blocks with real relative filepaths from the provided allowlist, or exactly NO_CHANGES.\n{EXECUTE_METHODOLOGY}",
                    },
                    {"role": "user", "content": retry_prompt},
                ]
            )
            raw_response = _clean_llm_response(raw_response)
            modifications = parse_llm_output(raw_response)

        modifications, filtered_errors = _filter_modifications_to_contract(
            modifications,
            round_contract,
            allowed_paths=execute_allowed_paths,
        )

        if not modifications:
            if filtered_errors:
                logger.warning("All modifications were filtered out by round contract")
                state["code_diff"] = (
                    "All proposed changes were outside the round contract and were rejected."
                )
                errors = state.get("execution_errors", []) or []
                errors.extend(filtered_errors)
                state["execution_errors"] = errors
            else:
                logger.warning("No modifications parsed from LLM output")
                state["code_diff"] = "No changes parsed from LLM output."
            return state

        diff_summary = []
        changelog_entries = []
        modified_files = []
        errors = state.get("execution_errors", []) or []
        errors.extend(filtered_errors)

        for mod in modifications:
            result = _apply_modification(
                project_path, mod, dry_run=dry_run, auto_mode=auto_mode
            )
            diff_summary.append(result)

            filepath = mod.get("filepath", "unknown_file")
            reason = mod.get("reason", "No reason provided")
            changelog_entries.append(f"- **{filepath}**: {reason}")

            if result.startswith("MODIFIED"):
                modified_files.append(filepath)
                logger.info(f"  ✅ {result}")
            elif result.startswith("BLOCKED"):
                errors.append(result)
                logger.warning(f"  🚫 {result}")
            elif result.startswith("DRY-RUN"):
                logger.info(f"  🏜️ {result}")
            elif result.startswith("SKIP"):
                errors.append(result)
                logger.warning(f"  ⚠️ {result}")
            else:
                logger.info(f"  {result}")

        final_diff = (
            "\n".join(diff_summary) if diff_summary else "No file changes proposed."
        )
        state["code_diff"] = final_diff
        state["execution_errors"] = errors
        state["modified_files"] = modified_files

        # Append to CHANGELOG.md
        if changelog_entries:
            changelog_path = os.path.join(project_path, ".opclog", "CHANGELOG.md")
            append_to_file(
                changelog_path,
                f"\n## Round {current_round}\n" + "\n".join(changelog_entries) + "\n",
            )

        applied_count = sum(1 for d in diff_summary if d.startswith("MODIFIED"))
        skipped_count = sum(1 for d in diff_summary if d.startswith("SKIP"))
        logger.info(f"Executed {applied_count} changes, skipped {skipped_count}.")

    except Exception as e:
        logger.error(f"Execution failed: {e}")
        state["code_diff"] = f"Execution failed: {e}"
        errors = state.get("execution_errors", []) or []
        errors.append(str(e))
        state["execution_errors"] = errors

    return state
