"""Architectural Context Generator (Opt-4).

Builds a compact (<800 tokens) "global architecture summary" for the target
project and persists it in OPC's external workspace (never inside the project).

This summary is injected at the TOP of every Execute-phase LLM prompt so the
model always sees the big picture, preventing locally-correct but
architecturally-wrong patches (Anti-patterns).

Storage: {workspace}/cache/arch_context.md
"""

import logging
import os
from typing import Optional

logger = logging.getLogger("opc.arch_context")

__all__ = [
    "generate_arch_context",
    "load_arch_context",
    "save_arch_context",
]

# Max characters we allow the arch context to occupy in a prompt (~800 tokens ≈ 3200 chars)
_MAX_CHARS = 3200


def _walk_top_dirs(project_path: str, profile: Optional[dict] = None) -> str:
    """Build a compact directory-role summary from the project root."""
    ignore_dirs = set((profile or {}).get("ignore_dirs", []))
    ignore_dirs.update({
        ".git", ".opclog", "node_modules", "__pycache__", "venv", ".venv",
        "dist", "build", "target", ".next", ".nuxt", ".idea", ".vscode",
        "vendor", "tmp", "log", ".pytest_cache",
    })

    lines = []
    try:
        entries = sorted(os.listdir(project_path))
    except OSError:
        return ""
    for entry in entries:
        full = os.path.join(project_path, entry)
        if os.path.isdir(full) and entry not in ignore_dirs:
            # Count immediate children to hint at importance
            try:
                child_count = len(os.listdir(full))
            except OSError:
                child_count = 0
            lines.append(f"  {entry}/  ({child_count} items)")
        elif os.path.isfile(full):
            lines.append(f"  {entry}")
    return "\n".join(lines[:60])  # cap at 60 entries


def generate_arch_context(
    project_path: str,
    profile: Optional[dict] = None,
    llm=None,
) -> str:
    """Generate a compact global architecture summary for the project.

    Strategy:
      1. Build a lightweight directory tree heuristic as baseline.
      2. If an LLM is available, ask it to annotate each top-level dir
         with a one-line role (View / Store / API / Utils / Config / Tests …).

    Returns a markdown string ≤ _MAX_CHARS.
    """
    project_type = (profile or {}).get("type", "unknown")
    dir_tree = _walk_top_dirs(project_path, profile)

    baseline = (
        f"# Project Architecture Overview\n"
        f"- **Type**: {project_type}\n"
        f"- **Root**: {project_path}\n\n"
        f"## Top-level Structure\n```\n{dir_tree}\n```\n\n"
        f"## Architectural Rules\n"
        f"- Do NOT create files outside the target files listed in the round contract.\n"
        f"- Do NOT alter build configuration files unless explicitly required.\n"
        f"- Respect the existing layer separation (View/Store/Service/Utils).\n"
    )

    if llm is None:
        logger.info("No LLM available for arch context; using structural baseline.")
        return baseline[:_MAX_CHARS]

    prompt = (
        f"You are an expert software architect reviewing a {project_type} project.\n"
        f"Project root: {project_path}\n\n"
        f"Top-level directory tree:\n```\n{dir_tree}\n```\n\n"
        f"Write a VERY CONCISE architectural summary (max 400 words) covering:\n"
        f"1. Bullet list: each significant top-level directory → its role "
        f"(e.g. `src/` → application source, `tests/` → unit tests).\n"
        f"2. 3-5 key architectural principles / constraints a developer MUST respect "
        f"when editing this codebase (e.g. 'All state lives in store/', "
        f"'API calls must go through services/', 'Never import from ui/ in utils/').\n\n"
        f"Format as clean markdown. Be extremely concise."
    )

    try:
        from utils.llm import LLMService
        content = llm.generate([
            {"role": "system", "content": "You are an expert software architect. Be concise."},
            {"role": "user", "content": prompt},
        ], temperature=0.1)
        logger.info(f"Arch context generated via LLM ({len(content)} chars).")
        # Prefix the baseline header
        full = f"# Project Architecture Overview\n- **Type**: {project_type}\n\n{content}"
        return full[:_MAX_CHARS]
    except Exception as exc:
        logger.warning(f"LLM arch context generation failed: {exc}. Using baseline.")
        return baseline[:_MAX_CHARS]


def save_arch_context(project_path: str, content: str) -> str:
    """Save arch context to OPC external workspace.

    Returns the file path where it was saved.
    """
    try:
        from utils.workspace import workspace_path
        fpath = workspace_path(project_path, "cache", "arch_context.md")
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Arch context saved to {fpath}")
        return fpath
    except Exception as exc:
        logger.warning(f"Failed to save arch context: {exc}")
        return ""


def load_arch_context(project_path: str) -> str:
    """Load a previously generated arch context from OPC external workspace.

    Returns empty string if not found.
    """
    try:
        from utils.workspace import workspace_path
        fpath = workspace_path(project_path, "cache", "arch_context.md")
        if os.path.isfile(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            logger.info(f"Arch context loaded from {fpath} ({len(content)} chars)")
            return content
    except Exception as exc:
        logger.warning(f"Failed to load arch context: {exc}")
    return ""
