"""Tests for `utils.skill_registry`."""

import pytest

from utils.skill_registry import SkillRegistry, SkillSpec, build_core_skill_registry


def _build_spec(name: str = "plan") -> SkillSpec:
    return SkillSpec(
        name=name,
        description=f"{name} skill",
        entrypoint=f"nodes.{name}:{name}_node",
        inputs=["state"],
        outputs=["state"],
        safety_level="medium",
    )


class TestSkillSpec:
    def test_requires_name_and_entrypoint(self):
        with pytest.raises(ValueError):
            SkillSpec(name="", description="x", entrypoint="nodes.plan:plan_node")

        with pytest.raises(ValueError):
            SkillSpec(name="plan", description="x", entrypoint="")

    def test_validates_safety_level(self):
        with pytest.raises(ValueError):
            SkillSpec(
                name="plan",
                description="x",
                entrypoint="nodes.plan:plan_node",
                safety_level="unsafe",
            )


class TestSkillRegistry:
    def test_register_and_get(self):
        registry = SkillRegistry()
        spec = _build_spec("plan")
        registry.register(spec)

        assert registry.has("plan") is True
        got = registry.get("plan")
        assert got is not None
        assert got.name == "plan"

    def test_list_enabled_only(self):
        registry = SkillRegistry()
        registry.register(_build_spec("execute"))
        registry.register(_build_spec("plan"))
        registry.disable("execute")

        enabled_names = [s.name for s in registry.list(enabled_only=True)]
        all_names = [s.name for s in registry.list(enabled_only=False)]

        assert enabled_names == ["plan"]
        assert all_names == ["execute", "plan"]

    def test_register_duplicate_raises(self):
        registry = SkillRegistry()
        registry.register(_build_spec("plan"))
        with pytest.raises(ValueError):
            registry.register(_build_spec("plan"))

    def test_register_many_duplicate_raises(self):
        registry = SkillRegistry()
        registry.register(_build_spec("plan"))
        with pytest.raises(ValueError):
            registry.register_many([_build_spec("plan"), _build_spec("execute")])

    def test_register_replace_existing_updates_spec(self):
        registry = SkillRegistry()
        registry.register(_build_spec("plan"))
        replacement = SkillSpec(
            name="plan",
            description="updated plan skill",
            entrypoint="nodes.plan:plan_node",
            safety_level="high",
        )
        registry.register(replacement, replace_existing=True)
        got = registry.get("plan")
        assert got is not None
        assert got.description == "updated plan skill"
        assert got.safety_level == "high"

    def test_query_and_toggle_missing_skill(self):
        registry = SkillRegistry()
        assert registry.get("missing") is None
        assert registry.has("missing") is False
        assert registry.disable("missing") is False
        assert registry.enable("missing") is False


class TestCoreRegistry:
    def test_build_core_skill_registry_contains_required_skills(self):
        registry = build_core_skill_registry()
        names = [s.name for s in registry.list(enabled_only=False)]
        assert names == ["execute", "plan", "report", "test"]
