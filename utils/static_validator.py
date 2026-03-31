"""Static code validator — flexible verification fallback (Opt-3).

When the target project's build/test environment is unavailable or
the build command returns environment-error codes (ENOENT, command not found,
missing modules), this module provides a language-aware STATIC validation
pass as a safe fallback instead of immediately marking the round as failed.

Supported modes:
  - Python  : py_compile (always available) + ruff check (optional)
  - JS/TS   : (syntax only via node --check, optional)
  - Generic : file-exists + encoding check only
"""

import logging
import os
import subprocess
import sys
from typing import Dict, List, Optional

logger = logging.getLogger("opc.static_validator")

__all__ = ["static_validate", "is_env_error"]

# Patterns that indicate the environment itself is broken (not the code)
_ENV_ERROR_PATTERNS = [
    "command not found",
    "is not recognized as an internal",   # Windows cmd
    "No such file or directory",
    "ENOENT",
    "Cannot find module",
    "cannot find",
    "not installed",
    "ModuleNotFoundError",
    "ImportError",
    "npm ERR! missing script",
    "npm warn",
    "Error: Cannot find",
]


def is_env_error(output: str) -> bool:
    """Return True if `output` looks like an environment/tooling error
    rather than a code error."""
    lowered = output.lower()
    return any(pat.lower() in lowered for pat in _ENV_ERROR_PATTERNS)


# ── Python Validation ───────────────────────────────────────────────────────

def _validate_python_files(files: List[str]) -> Dict:
    """Run py_compile + optional ruff on Python files."""
    errors: List[str] = []
    import py_compile
    for fpath in files:
        if not fpath.endswith(".py") or not os.path.isfile(fpath):
            continue
        try:
            py_compile.compile(fpath, doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"{fpath}: {exc}")
            continue

        # Optional: ruff check
        ruff_bin = _find_tool("ruff")
        if ruff_bin:
            result = subprocess.run(
                [ruff_bin, "check", "--output-format=text", fpath],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0 and result.stdout.strip():
                errors.append(f"ruff: {result.stdout.strip()[:500]}")

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "mode": "static_python",
    }


# ── JS/TS Validation ────────────────────────────────────────────────────────

def _validate_js_files(files: List[str], project_path: str) -> Dict:
    """Run eslint (if available) or node --check on JS/TS files."""
    errors: List[str] = []
    js_exts = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue"}
    js_files = [f for f in files if os.path.splitext(f)[1] in js_exts and os.path.isfile(f)]

    if not js_files:
        return {"passed": True, "errors": [], "mode": "static_js_empty"}

    # Try eslint
    eslint_bin = _find_tool("eslint", project_path)
    if eslint_bin:
        result = subprocess.run(
            [eslint_bin, "--format", "unix"] + js_files,
            capture_output=True, text=True, timeout=60, cwd=project_path
        )
        if result.returncode not in (0, 1):  # 2+ = fatal ESLint error
            errors.append(f"eslint fatal: {result.stderr.strip()[:300]}")
        elif result.stdout.strip():
            # Filter to errors only (not warnings)
            for line in result.stdout.splitlines():
                if ": error " in line:
                    errors.append(line.strip()[:200])
    else:
        # Fallback: node --check for plain JS
        node_bin = _find_tool("node")
        if node_bin:
            for fpath in js_files:
                if fpath.endswith((".ts", ".tsx", ".vue")):
                    continue  # node cannot check these without transpiling
                result = subprocess.run(
                    [node_bin, "--check", fpath],
                    capture_output=True, text=True, timeout=15
                )
                if result.returncode != 0:
                    errors.append(f"{fpath}: {result.stderr.strip()[:200]}")

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "mode": "static_js",
    }


# ── Generic Fallback ────────────────────────────────────────────────────────

def _validate_generic(files: List[str]) -> Dict:
    """Basic existence + encoding check for any file type."""
    errors: List[str] = []
    for fpath in files:
        if not os.path.isfile(fpath):
            errors.append(f"File not found after modification: {fpath}")
            continue
        try:
            with open(fpath, "r", encoding="utf-8", errors="strict") as f:
                f.read(4096)
        except UnicodeDecodeError:
            # Try latin-1
            try:
                with open(fpath, "r", encoding="latin-1") as f:
                    f.read(4096)
            except OSError as e:
                errors.append(f"{fpath}: encoding error — {e}")
        except OSError as e:
            errors.append(f"{fpath}: read error — {e}")
    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "mode": "static_generic",
    }


# ── Public API ──────────────────────────────────────────────────────────────

def static_validate(
    project_path: str,
    modified_files: List[str],
    profile: Optional[Dict] = None,
) -> Dict:
    """Run language-aware static validation on modified files.

    Args:
        project_path: Absolute path to the target project root.
        modified_files: List of relative paths (to project_path) of files
                        that were modified this round.
        profile: Optional project profile dict from `project_profile.py`.
                 Used to choose the appropriate validator.

    Returns:
        Dict with keys:
          - passed (bool)
          - errors (list[str])
          - mode (str): "static_python" | "static_js" | "static_generic"
    """
    if not modified_files:
        return {"passed": True, "errors": [], "mode": "static_noop"}

    abs_files = [
        os.path.join(project_path, f) if not os.path.isabs(f) else f
        for f in modified_files
    ]

    project_type = (profile or {}).get("type", "unknown")

    if project_type == "python" or all(f.endswith(".py") for f in abs_files if os.path.splitext(f)[1]):
        result = _validate_python_files(abs_files)
    elif project_type in ("javascript", "vue", "react"):
        result = _validate_js_files(abs_files, project_path)
    else:
        # Mixed or unknown: try python files first, then js, then generic
        py_files = [f for f in abs_files if f.endswith(".py")]
        js_exts = {".js", ".ts", ".jsx", ".tsx", ".vue"}
        js_files_list = [f for f in abs_files if os.path.splitext(f)[1] in js_exts]
        other_files = [f for f in abs_files if f not in py_files and f not in js_files_list]

        errors = []
        mode_parts = []
        if py_files:
            r = _validate_python_files(py_files)
            errors.extend(r["errors"])
            mode_parts.append(r["mode"])
        if js_files_list:
            r = _validate_js_files(js_files_list, project_path)
            errors.extend(r["errors"])
            mode_parts.append(r["mode"])
        if other_files:
            r = _validate_generic(other_files)
            errors.extend(r["errors"])
            mode_parts.append(r["mode"])
        result = {
            "passed": len(errors) == 0,
            "errors": errors,
            "mode": "+".join(mode_parts) if mode_parts else "static_generic",
        }

    if result["passed"]:
        logger.info(f"[static_validator] PASSED ({result['mode']}) — {len(abs_files)} file(s)")
    else:
        logger.warning(
            f"[static_validator] FAILED ({result['mode']}) — "
            f"{len(result['errors'])} error(s): {result['errors'][:2]}"
        )
    return result


# ── Helpers ─────────────────────────────────────────────────────────────────

def _find_tool(name: str, project_path: Optional[str] = None) -> Optional[str]:
    """Find an executable, checking node_modules/.bin and PATH."""
    import shutil
    # Check local node_modules/.bin first (project-local tools)
    if project_path:
        local_bin = os.path.join(project_path, "node_modules", ".bin", name)
        if sys.platform == "win32":
            for ext in ("", ".cmd", ".exe"):
                candidate = local_bin + ext
                if os.path.isfile(candidate):
                    return candidate
        else:
            if os.path.isfile(local_bin) and os.access(local_bin, os.X_OK):
                return local_bin
    return shutil.which(name)
