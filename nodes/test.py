import os
import shutil
import subprocess
import logging
import time
import difflib
from typing import List, Optional
from urllib.error import URLError
from urllib.request import urlopen
from state import OptimizerState
from utils.llm import LLMService
from utils.file_ops import write_to_file
from utils.methodology import REVIEW_METHODOLOGY

logger = logging.getLogger("opc.test")

FRONTEND_PROJECT_TYPES = {"javascript", "vue", "react"}


def _get_llm(state, node_key: str = "model") -> 'LLMService':
    """Get LLM instance from state config, with per-node model override."""
    cfg = state.get("llm_config", {}) or {}
    model = cfg.get(node_key) or cfg.get("model") or None
    timeout = cfg.get("timeout", 120)
    if model:
        return LLMService(model_name=model, timeout=timeout)
    return LLMService(timeout=timeout)

# ─── Subprocess Sandbox ──────────────────────────────────────────────

# Whitelist of allowed executable base names (lowercase)
ALLOWED_COMMANDS = {
    # Python
    "python", "python3", "python.exe", "py", "pytest", "pip", "pip3",
    # Node.js
    "npm", "npm.cmd", "npx", "npx.cmd", "node", "yarn", "yarn.cmd", "pnpm", "pnpm.cmd",
    # Java / Gradle
    "gradlew", "gradlew.bat", "gradle", "mvn", "mvn.cmd",
    # C/C++ / General
    "make", "cmake", "gcc", "g++", "clang",
    # Rust
    "cargo",
    # Go
    "go",
    # Flutter / Dart
    "flutter", "flutter.bat", "dart", "dart.bat",
    # Ruby
    "bundle", "bundle.bat", "rspec",
    # .NET
    "dotnet", "msbuild",
}

# Environment variables stripped from subprocess env for security
DANGEROUS_ENV_VARS = {
    "LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "LD_LIBRARY_PATH",
    "PYTHONSTARTUP", "PYTHONPATH", "NODE_OPTIONS",
}


def _build_safe_env() -> dict:
    """Build a sanitized subprocess environment."""
    return {k: v for k, v in os.environ.items() if k not in DANGEROUS_ENV_VARS}


def _run_sandboxed(
    cmd: List[str],
    cwd: str,
    timeout: int = 120,
    label: str = "",
    shell: bool = False,
) -> str:
    """Run a subprocess with sandbox protections.
    
    Validates command against ALLOWED_COMMANDS whitelist,
    strips dangerous environment variables, and applies timeouts.
    
    Returns a formatted result string.
    """
    # Validate command against whitelist
    exe = os.path.basename(cmd[0]).lower() if cmd else ""
    # For 'python -m pytest', also check the module name
    if exe not in ALLOWED_COMMANDS:
        msg = f"[{label}] BLOCKED: '{cmd[0]}' is not in the allowed commands whitelist"
        logger.warning(msg)
        return msg
    
    # Build a sanitized environment
    safe_env = _build_safe_env()
    
    # Build subprocess kwargs
    kwargs = {
        "cwd": cwd,
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "env": safe_env,
    }
    if shell:
        kwargs["shell"] = True
    # Windows: prevent console window popup
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    
    try:
        result = subprocess.run(cmd, **kwargs)
        output = (result.stdout + "\n" + result.stderr).strip()
        return f"[{label}] exit_code={result.returncode}\n{output}"
    except FileNotFoundError:
        return f"[{label}] command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return f"[{label}] TIMEOUT after {timeout}s"
    except OSError as e:
        return f"[{label}] OS error: {e}"


def _parse_cmd(cmd_str: str) -> List[str]:
    """Parse a command string into a list suitable for subprocess.

    Handles Windows-specific .cmd suffixes for npm/yarn/pnpm.
    E.g. "npm run build" → ["npm.cmd", "run", "build"] on Windows.
    """
    parts = cmd_str.strip().split()
    if not parts:
        return []
    # Windows: npm/yarn/pnpm need .cmd suffix
    if os.name == "nt" and parts[0] in ("npm", "yarn", "pnpm", "flutter", "dart"):
        parts[0] = parts[0] + ".cmd"
    return parts


def _run_build_check(project_path: str, profile: dict, timeout: int = 120) -> dict:
    """Run build command from project profile.

    Args:
        project_path: Project root directory.
        profile: Project profile dict with optional "build_cmd" key.
        timeout: Maximum seconds for build execution.

    Returns:
        {"passed": True/False, "output": str, "skipped": bool}
    """
    build_cmd = profile.get("build_cmd")
    if not build_cmd:
        return {"passed": True, "output": "No build command configured — skipped.", "skipped": True}

    cmd = _parse_cmd(build_cmd)
    if not cmd:
        return {"passed": True, "output": "Empty build command — skipped.", "skipped": True}

    logger.info(f"Running build: {build_cmd}")
    output = _run_sandboxed(cmd, cwd=project_path, timeout=timeout, label="build")

    passed = "exit_code=0" in output
    return {"passed": passed, "output": output, "skipped": False}


def _run_test_check(project_path: str, profile: dict, timeout: int = 120) -> dict:
    """Run test command from project profile.

    Args:
        project_path: Project root directory.
        profile: Project profile dict with optional "test_cmd" key.
        timeout: Maximum seconds for test execution.

    Returns:
        {"passed": True/False, "output": str, "skipped": bool}
    """
    test_cmd = profile.get("test_cmd")
    if not test_cmd:
        return {"passed": True, "output": "No test command configured — skipped.", "skipped": True}

    cmd = _parse_cmd(test_cmd)
    if not cmd:
        return {"passed": True, "output": "Empty test command — skipped.", "skipped": True}

    # Special handling for pytest: add useful flags
    if cmd[0] in ("pytest", "python") and "pytest" in test_cmd:
        if "--tb=short" not in cmd:
            cmd.append("--tb=short")
        if "-q" not in cmd:
            cmd.append("-q")

    logger.info(f"Running tests: {test_cmd}")
    output = _run_sandboxed(cmd, cwd=project_path, timeout=timeout, label="test")

    passed = "exit_code=0" in output
    return {"passed": passed, "output": output, "skipped": False}


def _default_dev_urls(profile: dict) -> List[str]:
    """Return likely local dev URLs for a frontend dev server."""
    env_url = os.environ.get("OPC_UI_URL", "").strip()
    if env_url:
        return [env_url]

    ptype = (profile.get("type") or "").lower()
    if ptype == "vue":
        return [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8080",
            "http://localhost:8080",
        ]
    if ptype == "react":
        return [
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    return [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8080",
        "http://localhost:8080",
    ]


def _start_dev_server(cmd: List[str], cwd: str):
    """Start a dev server in the background."""
    kwargs = {
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "env": _build_safe_env(),
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(cmd, **kwargs)


def _wait_for_dev_server(urls: List[str], timeout: int = 45) -> Optional[str]:
    """Poll candidate URLs until one responds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for url in urls:
            try:
                with urlopen(url, timeout=2) as response:
                    if getattr(response, "status", 200) < 500:
                        return url
            except (URLError, OSError, ValueError):
                continue
        time.sleep(1)
    return None


def _capture_ui_with_playwright(url: str, screenshot_path: str, timeout: int = 30) -> dict:
    """Capture a frontend page with Playwright and detect obvious runtime issues."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "passed": False,
            "output": "Playwright is not installed. Install `playwright` to enable UI verification.",
            "screenshot": None,
        }

    console_errors: List[str] = []
    page_errors: List[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        ready_state = page.evaluate("() => document.readyState")
        body_text = page.locator("body").inner_text(timeout=5000)
        page.screenshot(path=screenshot_path, full_page=True)
        browser.close()

    issues = []
    if ready_state != "complete":
        issues.append(f"document.readyState={ready_state}")
    if not body_text.strip():
        issues.append("empty body content")
    if console_errors:
        issues.append("console errors: " + " | ".join(console_errors[:3]))
    if page_errors:
        issues.append("page errors: " + " | ".join(page_errors[:3]))

    if issues:
        return {
            "passed": False,
            "output": f"UI verification failed for {url}: " + "; ".join(issues),
            "screenshot": screenshot_path,
        }
    return {
        "passed": True,
        "output": f"UI verification passed for {url}. Screenshot: {screenshot_path}",
        "screenshot": screenshot_path,
    }


def _terminate_process(process) -> None:
    """Terminate a background process safely."""
    if process is None:
        return
    try:
        process.terminate()
        process.wait(timeout=10)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def _extract_expected_diff_paths(round_contract: dict) -> dict:
    """Split expected-diff file paths into editable vs read-only buckets."""
    editable = set()
    readonly = set()
    for item in round_contract.get("expected_diff", []) or []:
        if not isinstance(item, str):
            continue
        parts = item.split(":", 1)
        if len(parts) != 2:
            continue
        head, detail = parts
        if not head.strip().lower().startswith("in "):
            continue
        path = head.strip()[3:].replace("\\", "/").lstrip("./")
        detail_lower = detail.strip().lower()
        if not path:
            continue
        if "no changes needed" in detail_lower:
            readonly.add(path)
        else:
            editable.add(path)
    return {"editable": editable, "readonly": readonly}


def _evaluate_round_outcome(state: OptimizerState, build_passed: bool) -> dict:
    """Assess whether the round delivered aligned, meaningful value."""
    round_contract = state.get("round_contract", {}) or {}
    modified_files = [str(path).replace("\\", "/") for path in (state.get("modified_files", []) or [])]
    code_diff = state.get("code_diff", "") or ""
    acceptance_checks = round_contract.get("acceptance_checks", []) or []
    expected_diff = round_contract.get("expected_diff", []) or []
    target_files = [str(path).replace("\\", "/") for path in (round_contract.get("target_files", []) or [])]
    path_info = _extract_expected_diff_paths(round_contract)
    readonly_paths = path_info["readonly"]
    editable_expected_paths = path_info["editable"]
    reasons = []

    effective_changes = bool(modified_files) and any(
        line.strip().startswith(("MODIFIED", "DRY-RUN"))
        for line in code_diff.splitlines()
        if line.strip()
    )
    if not effective_changes:
        reasons.append("No effective code changes were applied.")

    if not build_passed:
        reasons.append("Build/test/UI verification did not pass.")

    readonly_violations = [path for path in modified_files if path in readonly_paths]
    if readonly_violations:
        reasons.append(f"Read-only contract files were modified: {', '.join(readonly_violations)}")

    if editable_expected_paths:
        matched_expected_paths = [path for path in modified_files if path in editable_expected_paths]
        if not matched_expected_paths:
            reasons.append("Modified files did not match the contract's expected diff paths.")
    else:
        matched_expected_paths = [path for path in modified_files if not readonly_paths or path not in readonly_paths]

    out_of_scope_paths = [path for path in modified_files if target_files and path not in target_files]
    if out_of_scope_paths:
        reasons.append(f"Out-of-scope files were changed: {', '.join(out_of_scope_paths)}")

    # We no longer statically bind acceptance check completion to file counts.
    # Validation is deferred to either actual test commands or the Review LLM.
    unmet_acceptance_checks = []
    acceptance_hits = len(acceptance_checks) if (matched_expected_paths and effective_changes) else 0
    if acceptance_checks and acceptance_hits == 0:
        reasons.append("No valid expected file changes found, so acceptance checks are pending.")

    impact = int(round_contract.get("impact_score", 5) or 5)
    verification = int(round_contract.get("verification_score", 3) or 3)
    confidence = int(round_contract.get("confidence_score", 5) or 5)
    value_score = 0
    if build_passed:
        value_score += 2
    if matched_expected_paths:
        value_score += 4
    if effective_changes:
        value_score += 2
    if acceptance_hits:
        value_score += min(2, acceptance_hits)
    value_score = max(0, min(10, value_score))

    # ── Complexity penalty (autoresearch Occam's Razor) ───────────
    diff_lines = sum(1 for line in code_diff.splitlines() if line.strip())
    files_count = len(modified_files)
    if diff_lines > 100 and value_score < 6:
        value_score = max(0, value_score - 1)
        reasons.append(f"Complexity penalty: {diff_lines} diff lines but value_score only {value_score + 1}")
    if files_count > 5 and value_score < 6:
        value_score = max(0, value_score - 1)
        reasons.append(f"Scope penalty: {files_count} files changed but low value")

    objective_completed = (
        build_passed
        and effective_changes
        and not readonly_violations
        and bool(matched_expected_paths)
        and not unmet_acceptance_checks
    )
    aligned_with_plan = bool(matched_expected_paths) and not out_of_scope_paths and not readonly_violations
    low_value_round = (
        not objective_completed
        or value_score < max(4, min(7, (impact + verification + confidence) // 3))
    )
    replan_required = low_value_round or not aligned_with_plan

    summary = (
        f"objective_completed={objective_completed}; aligned_with_plan={aligned_with_plan}; "
        f"value_score={value_score}/10; modified_files={modified_files or ['(none)']}"
    )

    return {
        "objective_completed": objective_completed,
        "aligned_with_plan": aligned_with_plan,
        "low_value_round": low_value_round,
        "replan_required": replan_required,
        "value_score": value_score,
        "matched_expected_paths": matched_expected_paths,
        "readonly_violations": readonly_violations,
        "unmet_acceptance_checks": unmet_acceptance_checks,
        "reasons": reasons,
        "summary": summary,
        "change_magnitude": {"diff_lines": diff_lines, "files_count": files_count},
    }


def _collect_diff_evidence(project_path: str, modified_files: List[str]) -> str:
    """Collect real unified diffs from .bak files for review/reporting."""
    if not modified_files:
        return "No file-level diff evidence available."

    parts = []
    for filepath in modified_files:
        abs_path = os.path.join(project_path, filepath)
        bak_path = abs_path + ".bak"
        if not (os.path.exists(abs_path) and os.path.exists(bak_path)):
            parts.append(f"## {filepath}\n(diff unavailable: missing current file or .bak backup)")
            continue
        try:
            with open(bak_path, "r", encoding="utf-8", errors="replace") as f:
                old_lines = f.readlines()
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                new_lines = f.readlines()
            diff_lines = list(difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{filepath}",
                tofile=f"b/{filepath}",
                lineterm="",
            ))
            if diff_lines:
                parts.append(f"## {filepath}\n```diff\n" + "\n".join(diff_lines[:200]) + "\n```")
            else:
                parts.append(f"## {filepath}\n(no textual diff detected)")
        except Exception as e:
            parts.append(f"## {filepath}\n(diff collection failed: {e})")
    return "\n\n".join(parts)


def _run_ui_check(project_path: str, profile: dict, timeout: int = 60, round_num: int = 1) -> dict:
    """Run frontend UI verification with a local dev server + Playwright."""
    enabled = os.environ.get("OPC_ENABLE_UI_CHECK", "").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return {"passed": True, "output": "UI verification disabled - skipped.", "skipped": True}

    ptype = (profile.get("type") or "").lower()
    dev_cmd = profile.get("dev_cmd")
    if ptype not in FRONTEND_PROJECT_TYPES or not dev_cmd:
        return {"passed": True, "output": "No frontend UI verification configured - skipped.", "skipped": True}

    cmd = _parse_cmd(dev_cmd)
    if not cmd:
        return {"passed": True, "output": "Empty dev server command - skipped.", "skipped": True}

    output_lines = [f"Starting UI dev server: {dev_cmd}"]
    process = None
    try:
        process = _start_dev_server(cmd, cwd=project_path)
        url = _wait_for_dev_server(_default_dev_urls(profile), timeout=max(15, min(timeout, 45)))
        if not url:
            return {
                "passed": False,
                "output": "\n".join(output_lines + ["Timed out waiting for the frontend dev server to become ready."]),
                "skipped": False,
            }

        screenshot_dir = os.path.join(project_path, ".opclog", "ui_checks")
        os.makedirs(screenshot_dir, exist_ok=True)
        screenshot_path = os.path.join(screenshot_dir, f"round_{round_num}.png")
        capture = _capture_ui_with_playwright(url, screenshot_path, timeout=min(timeout, 30))
        output_lines.append(capture["output"])
        return {
            "passed": bool(capture.get("passed")),
            "output": "\n".join(output_lines),
            "skipped": False,
            "screenshot": capture.get("screenshot"),
            "url": url,
        }
    finally:
        _terminate_process(process)


def test_node(state: OptimizerState) -> OptimizerState:
    logger.info("--- 🧪 TEST PHASE ---")
    
    project_path = state["project_path"]
    code_diff = state.get("code_diff", "No changes made.")
    goal = state["optimization_goal"]
    build_timeout = int(os.environ.get("BUILD_TIMEOUT", "120"))
    
    # ── Load project profile (v2.11.0) ──────────────────────────
    profile = {}
    try:
        from utils.project_profile import load_project_profile
        profile = load_project_profile(project_path)
        logger.info(f"Using project profile: {profile.get('type', 'unknown')}")
    except Exception as e:
        logger.warning(f"Profile loading failed, using empty profile: {e}")

    # ── Opt-1: Fast-path (low complexity) ──────────────────────
    # For trivial tasks, skip full build + UI and run static validation only.
    if state.get("fast_path", False):
        logger.info("fast_path=True: running static validation only (skipping build/UI).")
        modified_files = state.get("modified_files", []) or []
        from utils.static_validator import static_validate
        sv_result = static_validate(project_path, modified_files, profile)
        build_passed = sv_result["passed"]
        combined_output = f"[fast-path static validation] {sv_result['mode']}\n" + "\n".join(sv_result["errors"][:10])
        round_evaluation = _evaluate_round_outcome(state, build_passed)
        diff_evidence = _collect_diff_evidence(project_path, modified_files)
        state["test_results"] = combined_output
        state["round_evaluation"] = round_evaluation
        state["build_result"] = {
            "build_passed": build_passed,
            "test_passed": build_passed,
            "ui_passed": True,
            "ui_skipped": True,
            "output": combined_output,
            "profile_type": profile.get("type", "unknown"),
            "round_evaluation": round_evaluation,
            "diff_evidence": diff_evidence,
            "validation_mode": "static_fallback",
        }
        # Still run LLM review for suggestions
        state["suggestions"] = f"Fast-path round. Static validation: {'PASSED' if build_passed else 'FAILED'}\n{combined_output}"
        logger.info(f"Fast-path validation: {'✅' if build_passed else '❌'} ({sv_result['mode']})")
        return state
    logger.info("Step 1: Running build verification...")

    # ── Opt-Auto-Test: Zero-config autonomous testing ──────────────────────
    if not profile.get("build_cmd") and not profile.get("test_cmd"):
        acceptance_checks = state.get("round_contract", {}).get("acceptance_checks", [])
        modified_files = state.get("modified_files", [])
        if acceptance_checks and modified_files:
            logger.info("No explicit test command configured. Autonomously inferring one...")
            try:
                infer_llm = _get_llm(state, "execute_model")
                infer_prompt = f"""Project type: {profile.get('type', 'unknown')}
Modified files: {modified_files}
Acceptance checks: {acceptance_checks}

Please extract exactly ONE short terminal command (e.g. `npx tsc --noEmit services/ai.ts`, `pytest tests/`, `npm run lint`) from the acceptance checks 
that can verify these changes. If the checks demand it, write the command.
If it is impossible to infer a safe, exact command, output exactly: NONE
Do not output markdown, explanations, or quotes. Only the raw command string."""
                
                inferred_cmd = infer_llm.generate([
                    {"role": "system", "content": "You are a test-command extraction bot. NO EXPLANATIONS. output safe bash commands or NONE."},
                    {"role": "user", "content": infer_prompt}
                ]).strip("`'\"\n ")
                
                if inferred_cmd and inferred_cmd != "NONE" and len(inferred_cmd) < 150:
                    profile["test_cmd"] = inferred_cmd
                    logger.info(f"🧠 Autonomously inferred test command: {inferred_cmd}")
            except Exception as e:
                logger.warning(f"Failed to autonomously infer test command: {e}")

    build_result = _run_build_check(project_path, profile, timeout=build_timeout)
    test_result = _run_test_check(project_path, profile, timeout=build_timeout)
    ui_result = _run_ui_check(
        project_path,
        profile,
        timeout=int(os.environ.get("UI_CHECK_TIMEOUT", "60")),
        round_num=state.get("current_round", 1),
    )
    
    # Combine results
    combined_output = build_result["output"] + "\n" + test_result["output"] + "\n" + ui_result["output"]
    build_passed = build_result["passed"] and test_result["passed"] and ui_result["passed"]

    # ── Opt-3: Env-error detection → static fallback ──────────────────────
    # If the build failed because the toolchain is missing (not a code error),
    # degrade to static validation instead of blaming the code change.
    from utils.static_validator import is_env_error, static_validate as _static_validate
    if not build_passed and is_env_error(combined_output):
        logger.warning("Env error detected in build output — downgrading to static validation.")
        _modified_sv = state.get("modified_files", []) or []
        sv_result = _static_validate(project_path, _modified_sv, profile)
        build_result = {
            "passed": sv_result["passed"],
            "output": f"[static fallback — env error] {sv_result['mode']}\n" + "\n".join(sv_result["errors"][:10]),
            "skipped": False,
        }
        test_result = {"passed": sv_result["passed"], "output": "skipped (env error fallback)", "skipped": True}
        ui_result = {"passed": True, "output": "skipped (env error fallback)", "skipped": True}
        combined_output = build_result["output"]
        build_passed = sv_result["passed"]
        if "build_result" not in state:
            state["build_result"] = {}
        state["build_result"]["validation_mode"] = "static_fallback"

    # If build failed, attempt LLM-driven fix before giving up
    max_self_repair = int(os.environ.get("OPC_MAX_SELF_REPAIR", "2"))
    modified_files = state.get("modified_files", []) or []
    if not build_passed and modified_files and max_self_repair > 0:
        repair_llm = _get_llm(state, "execute_model")
        feedback = ""
        for attempt in range(1, max_self_repair + 1):
            logger.info(f"🔧 Self-repair attempt {attempt}/{max_self_repair}...")
            try:
                repair_prompt = f"""The build/test failed with this output:
```
{combined_output[-3000:]}
```

Modified files: {modified_files}
Project path: {project_path}

Analyze the error and generate a SEARCH/REPLACE fix for the specific issue.
Only fix the build/syntax/import error — do NOT change logic or architecture.
Return ONLY one or more SEARCH/REPLACE blocks in this format:

FILE: <relative_path>
<<<<<<< SEARCH
exact lines to find
=======
replacement lines
>>>>>>> REPLACE
"""
                if feedback:
                    repair_prompt += f"\n\n{feedback}"

                repair_response = repair_llm.generate([
                    {"role": "system", "content": "You are a crash-repair agent. Fix only build errors, syntax errors, or import errors. Be minimal and precise. NO EXPLANATIONS REQUIRED. Output valid SEARCH/REPLACE blocks ONLY."},
                    {"role": "user", "content": repair_prompt}
                ])
                # Apply repair patches using existing diff parser
                from utils.diff_parser import parse_search_replace_blocks
                from utils.file_ops import read_file
                patches = parse_search_replace_blocks(repair_response)
                applied_any = False
                for patch in patches:
                    file_path = patch.get("file", "")
                    if not file_path:
                        continue
                    abs_repair_path = os.path.join(project_path, file_path)
                    if not os.path.exists(abs_repair_path):
                        continue
                    content = read_file(abs_repair_path)
                    if not content:
                        continue
                    search_text = patch.get("search", "")
                    replace_text = patch.get("replace", "")
                    if search_text and search_text in content:
                        new_content = content.replace(search_text, replace_text, 1)
                        with open(abs_repair_path, "w", encoding="utf-8") as f:
                            f.write(new_content)
                        applied_any = True
                        logger.info(f"  Applied repair patch to {file_path}")
                if not applied_any:
                    logger.warning(f"  Self-repair attempt {attempt}: no patches applied")
                    feedback = "SYSTEM ERROR: Your previous response contained no valid SEARCH/REPLACE blocks. You MUST output executable code modifications, not just explanations."
                    continue
                # Re-run build check
                build_result = _run_build_check(project_path, profile, timeout=build_timeout)
                test_result = _run_test_check(project_path, profile, timeout=build_timeout)
                combined_output = build_result["output"] + "\n" + test_result["output"] + "\n" + ui_result["output"]
                build_passed = build_result["passed"] and test_result["passed"] and ui_result["passed"]
                if build_passed:
                    logger.info(f"  ✅ Self-repair succeeded on attempt {attempt}")
                    break
                else:
                    logger.warning(f"  Self-repair attempt {attempt}: build still failing")
            except Exception as e:
                logger.warning(f"  Self-repair attempt {attempt} failed: {e}")
        if not build_passed:
            logger.warning("Self-repair exhausted, proceeding to rollback")

    round_evaluation = _evaluate_round_outcome(state, build_passed)
    diff_evidence = _collect_diff_evidence(project_path, list(state.get("modified_files", []) or []))
    
    state["test_results"] = combined_output
    state["round_evaluation"] = round_evaluation
    state["build_result"] = {
        "build_passed": build_result["passed"],
        "test_passed": test_result["passed"],
        "ui_passed": ui_result["passed"],
        "ui_skipped": ui_result.get("skipped", False),
        "ui_screenshot": ui_result.get("screenshot"),
        "ui_url": ui_result.get("url"),
        "output": combined_output,
        "profile_type": profile.get("type", "unknown"),
        "round_evaluation": round_evaluation,
        "diff_evidence": diff_evidence,
    }
    logger.info(
        f"Build: {'✅' if build_result['passed'] else '❌'} | "
        f"Test: {'✅' if test_result['passed'] else '❌'} | "
        f"UI: {'SKIP' if ui_result.get('skipped') else ('✅' if ui_result['passed'] else '❌')}"
    )
    
    # Log round evaluation (计数器统一由 interact_node 管理，test_node 不重复计数)
    logger.info(f"Round evaluation: {round_evaluation['summary']}")
    if not build_passed or round_evaluation["low_value_round"]:
        logger.warning(
            f"Round marked as non-improving (low_value={round_evaluation['low_value_round']}, "
            f"build_passed={build_passed}). Counter managed by interact_node."
        )
        # Auto-rollback only for technical failures (build error), not low-value-only rounds.
        modified_files = state.get("modified_files", []) or []
        if not build_passed and modified_files:
            logger.info(f"🔄 Auto-rolling back {len(modified_files)} modified files...")
            for filepath in modified_files:
                abs_path = os.path.join(project_path, filepath)
                bak_path = abs_path + ".bak"
                if os.path.exists(bak_path):
                    shutil.copy2(bak_path, abs_path)
                    logger.info(f"  ↩️ Restored: {filepath}")
            state["modified_files"] = []
    else:
        logger.info("Build passed and round is high-value. Counter will be reset by interact_node.")
    
    # Step 2: Testing Sub-Agent code review
    logger.info("Step 2: Spawning Testing Sub-Agent to review code_diff...")
    
    llm = _get_llm(state, "test_model")
    prompt = f"""You are the Testing & Review Agent for a code optimization workflow.
Target Project: {project_path}
Primary Objective: {goal}

Changes made in this round:
{code_diff}

Real diff evidence from modified files:
{diff_evidence}

Test execution output:
{combined_output}

Structured round contract:
{state.get("round_contract", {})}

Structured round evaluation:
{round_evaluation}

Based on the real diff evidence first, then the change summary and test results, evaluate if the objective is met, identify any new flaws, and provide extremely specific suggestions for the NEXT round of optimization.
Format your output as markdown. Write it to function as `优化建议.md`.

Your suggestions should include:
1. Assessment of this round's changes (what worked, what didn't)
2. Specific issues found (with file paths and line references if possible)
3. Concrete next-round optimization suggestions ordered by priority
4. Whether you see signs of diminishing returns (to help decide when to stop)
5. If `replan_required` is true, start with a short `Replan Required` section that states exactly why this round was low-value or misaligned
6. If diff evidence is unavailable, say that explicitly instead of pretending to have reviewed the implementation
{REVIEW_METHODOLOGY}
"""
    
    try:
        new_suggestions = llm.generate([
            {"role": "system", "content": f"You are the Testing & Review Agent. Evaluate code changes based on test results and provide actionable suggestions for the next optimization round. Use markdown format.\n{REVIEW_METHODOLOGY}"},
            {"role": "user", "content": prompt}
        ])
        state["suggestions"] = new_suggestions
        
        # Save suggestions to external workspace (Opt-6)
        try:
            from utils.workspace import workspace_path
            suggestions_path = workspace_path(project_path, "logs", "suggestions.md")
        except Exception:
            suggestions_path = os.path.join(project_path, ".opclog", "suggestions.md")
        write_to_file(suggestions_path, new_suggestions)
            
        logger.info(f"Updated and saved new suggestions to {suggestions_path}")
    except Exception as e:
        logger.error(f"Test agent review failed: {e}")
        state["suggestions"] = f"Review failed: {e}"
        
    return state
