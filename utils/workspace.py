"""OPC External Workspace Manager (Opt-6).

Keeps all OPC-generated artifacts (logs, backups, reports, cache files)
OUT of the target project directory. Each target project gets a unique
sub-directory derived from its path hash inside OPC_HOME.

Directory layout:
  {OPC_HOME}/.opc_workspace/
    {project_hash}/           ← one folder per target project
      logs/                   ← plan.md, round_contract.json, etc.
      backups/                ← migrated .bak files after round end
      reports/                ← round + final reports
      cache/                  ← project_profile.json, arch_context.md

Environment variables:
  OPC_HOME  — Override the root home dir.
               Defaults to %USERPROFILE%\.opc (Windows) or ~/.opc (Unix).
"""

import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger("opc.workspace")

__all__ = [
    "get_workspace_dir",
    "workspace_path",
    "get_opc_home",
]


def get_opc_home() -> str:
    """Return the OPC home directory, creating it if necessary."""
    env_home = os.environ.get("OPC_HOME", "")
    if env_home:
        home = env_home
    else:
        # Windows: %USERPROFILE%\.opc  |  Unix: ~/.opc
        user_home = os.path.expanduser("~")
        home = os.path.join(user_home, ".opc")
    os.makedirs(home, exist_ok=True)
    return home


def _project_hash(project_path: str) -> str:
    """Return a stable 8-char hex hash for a project path."""
    normalized = os.path.normcase(os.path.abspath(project_path))
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:8]


def get_workspace_dir(project_path: str) -> str:
    """Return (and create) the external workspace directory for a project.

    Args:
        project_path: Absolute path to the target project.

    Returns:
        Absolute path to  {OPC_HOME}/.opc_workspace/{project_hash}/
    """
    opc_home = get_opc_home()
    phash = _project_hash(project_path)
    ws_dir = os.path.join(opc_home, ".opc_workspace", phash)
    # Ensure all sub-directories exist
    for sub in ("logs", "backups", "reports", "cache"):
        os.makedirs(os.path.join(ws_dir, sub), exist_ok=True)
    # Write a human-readable breadcrumb so the user knows which project this is
    breadcrumb = os.path.join(ws_dir, "PROJECT_PATH.txt")
    if not os.path.exists(breadcrumb):
        try:
            with open(breadcrumb, "w", encoding="utf-8") as f:
                f.write(project_path + "\n")
        except OSError:
            pass
    return ws_dir


def workspace_path(project_path: str, *parts: str) -> str:
    """Join parts under the project's external workspace directory.

    Example:
        workspace_path(proj, "logs", "round_1_plan.md")
        → ~/.opc/.opc_workspace/a3b8d1b6/logs/round_1_plan.md
    """
    ws = get_workspace_dir(project_path)
    return os.path.join(ws, *parts)
