"""LLM Trace Logger — records every LLM call for replay and debugging (v2.6.0).

Zero-invasion approach: the logger is a global singleton that LLMService
writes to after each successful call. `safe_node_wrapper` sets the current
node/round context before each node runs.

Storage: JSONL files under `.opclog/traces/round_{n}.jsonl`.
"""

import os
import json
import time
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("opc.trace")

# ─── Data Structures ──────────────────────────────────────────────

class TraceEntry:
    """One LLM call record."""
    __slots__ = (
        "node_name", "round_number", "timestamp", "model_name",
        "input_messages", "output_text", "prompt_tokens",
        "completion_tokens", "elapsed_seconds",
    )

    def __init__(
        self,
        node_name: str = "",
        round_number: int = 0,
        timestamp: str = "",
        model_name: str = "",
        input_messages: Optional[List[Dict[str, str]]] = None,
        output_text: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        elapsed_seconds: float = 0.0,
    ):
        self.node_name = node_name
        self.round_number = round_number
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.model_name = model_name
        self.input_messages = input_messages or []
        self.output_text = output_text
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.elapsed_seconds = elapsed_seconds

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}

    @classmethod
    def from_dict(cls, d: dict) -> "TraceEntry":
        return cls(**{k: d[k] for k in cls.__slots__ if k in d})


# ─── TraceLogger Singleton ────────────────────────────────────────

class TraceLogger:
    """Global trace collector."""

    def __init__(self) -> None:
        self._entries: List[TraceEntry] = []
        self._lock = threading.Lock()
        # Current context (set by safe_node_wrapper before each node)
        self._node_name: str = ""
        self._round_number: int = 0

    # ── Context ───────────────────────────────────────────────────

    def set_context(self, node_name: str, round_number: int) -> None:
        """Set the current node/round so log() picks them up automatically."""
        self._node_name = node_name
        self._round_number = round_number

    # ── Recording ─────────────────────────────────────────────────

    def log(
        self,
        model_name: str,
        input_messages: List[Dict[str, str]],
        output_text: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        elapsed_seconds: float = 0.0,
        node_name: str = "",
        round_number: int = 0,
    ) -> None:
        """Record one LLM call."""
        entry = TraceEntry(
            node_name=node_name or self._node_name,
            round_number=round_number or self._round_number,
            model_name=model_name,
            input_messages=input_messages,
            output_text=output_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            elapsed_seconds=elapsed_seconds,
        )
        with self._lock:
            self._entries.append(entry)
        logger.debug(
            f"Trace: {entry.node_name} R{entry.round_number} "
            f"{entry.prompt_tokens}+{entry.completion_tokens} tok"
        )

    # ── Query ─────────────────────────────────────────────────────

    def get_round(self, round_num: int) -> List[dict]:
        """Return all entries for a given round as dicts."""
        with self._lock:
            return [e.to_dict() for e in self._entries if e.round_number == round_num]

    def get_all_rounds(self) -> Dict[int, List[dict]]:
        """Return entries grouped by round number."""
        rounds: Dict[int, List[dict]] = {}
        with self._lock:
            for e in self._entries:
                rounds.setdefault(e.round_number, []).append(e.to_dict())
        return rounds

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    # ── Persistence ───────────────────────────────────────────────

    def save_round(self, project_path: str, round_num: int) -> Optional[str]:
        """Persist one round's traces to JSONL. Returns the file path."""
        entries = self.get_round(round_num)
        if not entries:
            return None

        traces_dir = os.path.join(project_path, ".opclog", "traces")
        os.makedirs(traces_dir, exist_ok=True)
        path = os.path.join(traces_dir, f"round_{round_num}.jsonl")

        try:
            with open(path, "w", encoding="utf-8") as f:
                for entry in entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            logger.info(f"Saved {len(entries)} trace entries → {path}")
            return path
        except Exception as exc:
            logger.warning(f"Failed to save trace: {exc}")
            return None

    def export_round_json(self, round_num: int) -> str:
        """Export one round's traces as a formatted JSON string."""
        entries = self.get_round(round_num)
        return json.dumps(entries, ensure_ascii=False, indent=2)

    @staticmethod
    def load_round(project_path: str, round_num: int) -> List[dict]:
        """Load a round's traces from JSONL file on disk."""
        path = os.path.join(project_path, ".opclog", "traces", f"round_{round_num}.jsonl")
        if not os.path.exists(path):
            return []
        entries = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except Exception as exc:
            logger.warning(f"Failed to load trace {path}: {exc}")
        return entries


# ─── Global Accessor ──────────────────────────────────────────────

_instance: Optional[TraceLogger] = None
_instance_lock = threading.Lock()


def get_trace_logger() -> TraceLogger:
    """Get or create the global TraceLogger singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = TraceLogger()
    return _instance
