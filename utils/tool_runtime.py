"""Runtime helpers for controlled Agent tool calls."""

from __future__ import annotations

import importlib
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Optional

try:
    from .tool_registry import ToolRegistry, build_core_tool_registry
except ImportError:
    from utils.tool_registry import ToolRegistry, build_core_tool_registry


@dataclass
class ToolCallResult:
    """Normalized result returned by one tool invocation."""

    tool_name: str
    ok: bool
    output: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error_type: str = ""
    retryable: bool = False
    elapsed: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _load_entrypoint(entrypoint: str) -> Callable[..., Any]:
    if ":" not in entrypoint:
        raise ValueError(f"Invalid tool entrypoint: {entrypoint}")
    module_name, attr_name = entrypoint.split(":", 1)
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        package_root = (__package__ or "").split(".", 1)[0]
        if not package_root:
            raise
        module = importlib.import_module(f"{package_root}.{module_name}")
    handler = getattr(module, attr_name)
    if not callable(handler):
        raise TypeError(f"Tool entrypoint is not callable: {entrypoint}")
    return handler


def _validate_payload_paths(payload: dict, project_path: str) -> Optional[str]:
    """Block obvious path traversal for path-bearing tool payloads."""
    if not project_path:
        return None

    root = os.path.abspath(project_path)
    for key in ("path", "filepath", "file_path"):
        raw = payload.get(key)
        if not raw:
            continue
        path_text = str(raw).replace("\\", "/").strip()
        if os.path.isabs(path_text):
            return f"{key} must be project-relative: {raw}"
        candidate = os.path.abspath(os.path.join(root, path_text))
        try:
            if os.path.commonpath([root, candidate]) != root:
                return f"{key} escapes project directory: {raw}"
        except ValueError:
            return f"{key} escapes project directory: {raw}"
    return None


def _emit(event_type: str, data: dict) -> None:
    try:
        from ui.web_server import emit

        emit(event_type, data)
    except Exception:
        pass


def _summarize_output(output: str, limit: int = 220) -> str:
    text = (output or "").strip().replace("\r", "")
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _append_call(state: dict, result: ToolCallResult) -> None:
    calls = list(state.get("tool_calls", []) or [])
    item = result.to_dict()
    item["round"] = state.get("current_round", 1)
    item["output_summary"] = _summarize_output(result.output)
    calls.append(item)
    state["tool_calls"] = calls
    if result.error_type:
        state["failure_type"] = result.error_type
        state["fallback_reason"] = f"tool_call_failed:{result.tool_name}"


def _normalize_result(tool_name: str, raw: Any, elapsed: float) -> ToolCallResult:
    if isinstance(raw, ToolCallResult):
        raw.tool_name = tool_name
        raw.elapsed = round(elapsed, 3)
        return raw
    if isinstance(raw, dict):
        ok = bool(raw.get("passed", raw.get("ok", True)))
        output = str(raw.get("output", raw.get("docs", "")) or "")
        return ToolCallResult(
            tool_name=tool_name,
            ok=ok,
            output=output,
            data=dict(raw),
            elapsed=round(elapsed, 3),
        )
    output = "" if raw is None else str(raw)
    return ToolCallResult(
        tool_name=tool_name,
        ok=True,
        output=output,
        data={"value": raw},
        elapsed=round(elapsed, 3),
    )


def run_tool(
    tool_name: str,
    payload: dict,
    state: dict,
    *,
    registry: ToolRegistry | None = None,
    handlers: Dict[str, Callable[[dict, dict], Any]] | None = None,
) -> ToolCallResult:
    """Run a named tool, record observability, and return a normalized result."""
    active_registry = registry or build_core_tool_registry()
    spec = active_registry.get(tool_name)
    if spec is None:
        result = ToolCallResult(
            tool_name=tool_name,
            ok=False,
            error_type="tool_missing",
            output=f"Tool not registered: {tool_name}",
        )
        _append_call(state, result)
        return result

    if not spec.enabled:
        result = ToolCallResult(
            tool_name=tool_name,
            ok=False,
            error_type="tool_disabled",
            output=f"Tool disabled: {tool_name}",
        )
        _append_call(state, result)
        return result

    project_path = str(payload.get("project_path") or state.get("project_path", ""))
    path_error = _validate_payload_paths(payload, project_path)
    if path_error:
        result = ToolCallResult(
            tool_name=tool_name,
            ok=False,
            error_type="tool_path_violation",
            output=path_error,
        )
        _append_call(state, result)
        return result

    start = time.time()
    state["agent_loop_step"] = "act"
    _emit(
        "tool_call_start",
        {
            "tool": tool_name,
            "round": state.get("current_round", 1),
            "agent": state.get("active_agent", ""),
        },
    )

    try:
        handler = (handlers or {}).get(tool_name) or _load_entrypoint(spec.entrypoint)
        try:
            raw = handler(payload, state)
        except TypeError:
            raw = handler(**payload)
        result = _normalize_result(tool_name, raw, time.time() - start)
    except Exception as exc:
        result = ToolCallResult(
            tool_name=tool_name,
            ok=False,
            output=str(exc),
            error_type=f"tool_{type(exc).__name__.lower()}",
            retryable=False,
            elapsed=round(time.time() - start, 3),
        )

    state["agent_loop_step"] = "observe"
    _append_call(state, result)
    _emit(
        "tool_call_complete",
        {
            "tool": tool_name,
            "round": state.get("current_round", 1),
            "ok": result.ok,
            "elapsed": result.elapsed,
            "error_type": result.error_type,
            "output_summary": _summarize_output(result.output),
        },
    )
    return result
