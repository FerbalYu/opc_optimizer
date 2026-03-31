"""Checkpoint utility for serializing and restoring optimizer state.

Includes cross-platform file locking to prevent corruption from
concurrent writes.
"""

import os
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("opc.checkpoint")

CHECKPOINT_FILENAME = "checkpoint.json"


# ─── Cross-platform file lock ─────────────────────────────────────────

class _FileLock:
    """Simple cross-platform file lock using msvcrt (Windows) or fcntl (Unix)."""

    def __init__(self, lock_path: str):
        self.lock_path = lock_path
        self._fd: Optional[int] = None

    def __enter__(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.lock_path)) or '.', exist_ok=True)
        self._fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_EX)
        except (IOError, OSError):
            logger.warning("Could not acquire file lock, proceeding without lock")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._fd is not None:
            try:
                if os.name == "nt":
                    import msvcrt
                    try:
                        msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                    except (IOError, OSError):
                        pass
                else:
                    import fcntl
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None
        return False


# ─── Checkpoint operations ─────────────────────────────────────────────

def save_checkpoint(project_path: str, state: Dict[str, Any]) -> str:
    """Save current optimizer state to a checkpoint file.
    
    Uses file locking to prevent corruption from concurrent writes.
    Returns the checkpoint file path.
    """
    checkpoint_dir = os.path.join(project_path, ".opclog")
    os.makedirs(checkpoint_dir, exist_ok=True)
    checkpoint_path = os.path.join(checkpoint_dir, CHECKPOINT_FILENAME)
    lock_path = checkpoint_path + ".lock"
    
    # Only serialize JSON-safe fields
    serializable = {}
    for key, value in state.items():
        if isinstance(value, (str, int, float, bool, list)):
            serializable[key] = value
        else:
            serializable[key] = str(value)
    
    with _FileLock(lock_path):
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Checkpoint saved: Round {state.get('current_round', '?')}")
    return checkpoint_path


def load_checkpoint(project_path: str) -> Optional[Dict[str, Any]]:
    """Load optimizer state from a checkpoint file.
    
    Uses file locking to prevent reading a partially-written file.
    Returns the state dict, or None if no checkpoint exists.
    """
    checkpoint_path = os.path.join(project_path, ".opclog", CHECKPOINT_FILENAME)
    
    if not os.path.exists(checkpoint_path):
        logger.info("No checkpoint found")
        return None
    
    lock_path = checkpoint_path + ".lock"
    
    try:
        with _FileLock(lock_path):
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
        
        # Ensure critical fields have correct types
        state.setdefault("current_round", 1)
        state.setdefault("should_stop", False)
        state.setdefault("round_reports", [])
        state.setdefault("execution_errors", [])
        state.setdefault("modified_files", [])
        state.setdefault("round_contract", {})
        state.setdefault("round_evaluation", {})
        state.setdefault("active_tasks", [])
        state.setdefault("ui_preferences", {"skip_plan_review": False})
        
        logger.info(f"Checkpoint loaded: Round {state.get('current_round')}")
        return state
        
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load checkpoint: {e}")
        return None


def clear_checkpoint(project_path: str) -> None:
    """Remove the checkpoint file."""
    checkpoint_path = os.path.join(project_path, ".opclog", CHECKPOINT_FILENAME)
    if os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)
        logger.info("Checkpoint cleared")
    # Also clean up lock file
    lock_path = checkpoint_path + ".lock"
    if os.path.exists(lock_path):
        try:
            os.remove(lock_path)
        except OSError:
            pass
