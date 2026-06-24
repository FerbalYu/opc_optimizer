"""Tests for `utils.tool_registry`."""

import pytest

from utils.tool_registry import ToolRegistry, ToolSpec, build_core_tool_registry


def test_tool_spec_requires_name_and_entrypoint():
    with pytest.raises(ValueError):
        ToolSpec(name="", description="x", entrypoint="module:fn")
    with pytest.raises(ValueError):
        ToolSpec(name="x", description="x", entrypoint="")


def test_tool_registry_register_query_and_toggle():
    registry = ToolRegistry()
    spec = ToolSpec(name="build_check", description="build", entrypoint="x:y")

    registry.register(spec)

    assert registry.has("build_check") is True
    assert registry.get("build_check") == spec
    assert registry.list()[0].name == "build_check"
    assert registry.disable("build_check") is True
    assert registry.list() == []
    assert registry.list(enabled_only=False)[0].enabled is False
    assert registry.enable("build_check") is True


def test_tool_registry_duplicate_requires_replace():
    registry = ToolRegistry()
    registry.register(ToolSpec(name="x", description="x", entrypoint="a:b"))

    with pytest.raises(ValueError):
        registry.register(ToolSpec(name="x", description="new", entrypoint="a:c"))

    registry.register(
        ToolSpec(name="x", description="new", entrypoint="a:c"),
        replace_existing=True,
    )
    assert registry.get("x").description == "new"


def test_core_tool_registry_contains_verification_tools():
    registry = build_core_tool_registry()

    for name in ("build_check", "test_check", "ui_check", "context7_docs"):
        assert registry.has(name)
