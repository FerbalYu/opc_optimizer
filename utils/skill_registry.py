"""Skill registry primitives for the skillized workflow foundation.

Phase 1 goal:
- Define a stable `SkillSpec` contract.
- Provide an in-memory `SkillRegistry` with basic lifecycle operations.
"""

from dataclasses import dataclass, field, replace
from typing import Dict, List, Literal, Optional

SafetyLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class SkillSpec:
    """Static metadata for one executable skill."""

    name: str
    description: str
    entrypoint: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    safety_level: SafetyLevel = "medium"
    enabled: bool = True
    resources: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Skill name must be non-empty")
        if not self.entrypoint or not self.entrypoint.strip():
            raise ValueError("Skill entrypoint must be non-empty")
        if self.safety_level not in ("low", "medium", "high"):
            raise ValueError("Skill safety_level must be one of: low, medium, high")


class SkillRegistry:
    """In-memory registry for `SkillSpec` objects."""

    def __init__(self) -> None:
        self._skills: Dict[str, SkillSpec] = {}

    def register(self, spec: SkillSpec, replace_existing: bool = False) -> None:
        """Register a skill; raises on duplicates unless replacement is allowed."""
        if spec.name in self._skills and not replace_existing:
            raise ValueError(f"Skill already registered: {spec.name}")
        self._skills[spec.name] = spec

    def register_many(self, specs: List[SkillSpec], replace_existing: bool = False) -> None:
        """Register multiple specs with the same conflict strategy."""
        for spec in specs:
            self.register(spec, replace_existing=replace_existing)

    def get(self, name: str) -> Optional[SkillSpec]:
        """Return one skill by name."""
        return self._skills.get(name)

    def has(self, name: str) -> bool:
        """Return whether a skill exists."""
        return name in self._skills

    def list(self, enabled_only: bool = True) -> List[SkillSpec]:
        """List skills sorted by name."""
        skills = sorted(self._skills.values(), key=lambda s: s.name)
        if not enabled_only:
            return skills
        return [spec for spec in skills if spec.enabled]

    def disable(self, name: str) -> bool:
        """Disable one skill; returns False when skill is missing."""
        spec = self.get(name)
        if spec is None:
            return False
        self._skills[name] = replace(spec, enabled=False)
        return True

    def enable(self, name: str) -> bool:
        """Enable one skill; returns False when skill is missing."""
        spec = self.get(name)
        if spec is None:
            return False
        self._skills[name] = replace(spec, enabled=True)
        return True


def build_core_skill_registry() -> SkillRegistry:
    """Build registry with baseline workflow skills.

    These skills mirror the current stable linear pipeline and are the
    minimum set required by `create_optimizer_graph`.
    """
    registry = SkillRegistry()
    registry.register_many(
        [
            SkillSpec(
                name="plan",
                description="Generate optimization plan",
                entrypoint="nodes.plan:plan_node",
                inputs=["state"],
                outputs=["state"],
                safety_level="medium",
                enabled=True,
            ),
            SkillSpec(
                name="execute",
                description="Apply code modifications from plan",
                entrypoint="nodes.execute:execute_node",
                inputs=["state"],
                outputs=["state"],
                safety_level="high",
                enabled=True,
            ),
            SkillSpec(
                name="test",
                description="Run verification and quality checks",
                entrypoint="nodes.test:test_node",
                inputs=["state"],
                outputs=["state"],
                safety_level="medium",
                enabled=True,
            ),
            SkillSpec(
                name="report",
                description="Generate round report and metrics",
                entrypoint="nodes.report:report_node",
                inputs=["state"],
                outputs=["state"],
                safety_level="low",
                enabled=True,
            ),
        ]
    )
    return registry
