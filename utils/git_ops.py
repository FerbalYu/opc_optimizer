"""Git operations utility for automated version control integration."""

import os
import subprocess
import logging
from typing import Optional

logger = logging.getLogger("opc.git")


def is_git_repo(project_path: str) -> bool:
    """Check if the project directory is a git repository."""
    return os.path.isdir(os.path.join(project_path, ".git"))


def git_init(project_path: str) -> bool:
    """Initialize a git repository if one doesn't exist."""
    if is_git_repo(project_path):
        return True
    try:
        subprocess.run(["git", "init"], cwd=project_path,
                       capture_output=True, text=True, timeout=30, check=True)
        logger.info(f"Initialized git repository in {project_path}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.warning(f"Failed to initialize git: {e}")
        return False


def git_auto_commit(project_path: str, round_num: int, summary: str = "") -> bool:
    """Stage all changes and create an auto-commit for the current round."""
    if not is_git_repo(project_path):
        logger.debug("Not a git repo, skipping auto-commit")
        return False
    
    try:
        # Stage all changes
        subprocess.run(["git", "add", "-A"], cwd=project_path,
                       capture_output=True, text=True, timeout=30, check=True)
        
        # Check if there are staged changes
        result = subprocess.run(["git", "diff", "--cached", "--quiet"],
                               cwd=project_path, capture_output=True, timeout=10)
        if result.returncode == 0:
            logger.info("No staged changes to commit")
            return True
        
        # Commit
        commit_msg = f"[OPC] Round {round_num} optimization"
        if summary:
            commit_msg += f"\n\n{summary[:500]}"
        
        subprocess.run(["git", "commit", "-m", commit_msg],
                       cwd=project_path, capture_output=True, text=True,
                       timeout=30, check=True)
        logger.info(f"Auto-committed: Round {round_num}")
        return True
        
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.warning(f"Auto-commit failed: {e}")
        return False


def git_stash(project_path: str) -> bool:
    """Stash current changes before making modifications."""
    if not is_git_repo(project_path):
        return False
    try:
        subprocess.run(["git", "stash", "push", "-m", "OPC pre-optimization stash"],
                       cwd=project_path, capture_output=True, text=True,
                       timeout=30, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def git_diff_summary(project_path: str) -> str:
    """Get a summary of current unstaged changes."""
    if not is_git_repo(project_path):
        return ""
    try:
        result = subprocess.run(["git", "diff", "--stat"],
                               cwd=project_path, capture_output=True, text=True, timeout=30)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
