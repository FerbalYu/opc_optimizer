"""Tests for `utils.tool_runtime`."""

from utils.tool_registry import ToolRegistry, ToolSpec
from utils.tool_runtime import run_tool


def _registry(enabled=True):
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="sample",
            description="sample",
            entrypoint="tests.test_tool_runtime:sample_entrypoint",
            enabled=enabled,
        )
    )
    return registry


def sample_entrypoint(payload, state):
    return {"passed": True, "output": f"ok:{payload['value']}", "skipped": False}


def test_run_tool_records_successful_call(tmp_path):
    state = {"project_path": str(tmp_path), "current_round": 2}

    result = run_tool(
        "sample",
        {"project_path": str(tmp_path), "value": "ready"},
        state,
        registry=_registry(),
        handlers={"sample": sample_entrypoint},
    )

    assert result.ok is True
    assert result.output == "ok:ready"
    assert state["agent_loop_step"] == "observe"
    assert state["tool_calls"][0]["tool_name"] == "sample"
    assert state["tool_calls"][0]["round"] == 2


def test_run_tool_reports_disabled_tool(tmp_path):
    state = {"project_path": str(tmp_path)}

    result = run_tool(
        "sample",
        {"project_path": str(tmp_path)},
        state,
        registry=_registry(enabled=False),
    )

    assert result.ok is False
    assert result.error_type == "tool_disabled"
    assert state["failure_type"] == "tool_disabled"
    assert state["fallback_reason"] == "tool_call_failed:sample"


def test_run_tool_blocks_path_escape(tmp_path):
    state = {"project_path": str(tmp_path)}

    result = run_tool(
        "sample",
        {"project_path": str(tmp_path), "filepath": "../outside.py"},
        state,
        registry=_registry(),
    )

    assert result.ok is False
    assert result.error_type == "tool_path_violation"


def test_run_tool_records_handler_exception(tmp_path):
    def boom(_payload, _state):
        raise RuntimeError("bad tool")

    state = {"project_path": str(tmp_path)}
    result = run_tool(
        "sample",
        {"project_path": str(tmp_path)},
        state,
        registry=_registry(),
        handlers={"sample": boom},
    )

    assert result.ok is False
    assert result.error_type == "tool_runtimeerror"
    assert state["failure_type"] == "tool_runtimeerror"
