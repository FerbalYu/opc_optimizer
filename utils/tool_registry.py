"""Tool registry primitives for controlled Agent tool calling."""

from dataclasses import dataclass, field, replace
from typing import Dict, List, Literal, Optional

SafetyLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class ToolSpec:
    """Static metadata for one callable tool."""

    name: str
    description: str
    entrypoint: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    safety_level: SafetyLevel = "medium"
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Tool name must be non-empty")
        if not self.entrypoint or not self.entrypoint.strip():
            raise ValueError("Tool entrypoint must be non-empty")
        if self.safety_level not in ("low", "medium", "high"):
            raise ValueError("Tool safety_level must be one of: low, medium, high")


class ToolRegistry:
    """In-memory registry for Agent tools."""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec, replace_existing: bool = False) -> None:
        if spec.name in self._tools and not replace_existing:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def register_many(
        self, specs: List[ToolSpec], replace_existing: bool = False
    ) -> None:
        for spec in specs:
            self.register(spec, replace_existing=replace_existing)

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def list(self, enabled_only: bool = True) -> List[ToolSpec]:
        tools = sorted(self._tools.values(), key=lambda spec: spec.name)
        if not enabled_only:
            return tools
        return [spec for spec in tools if spec.enabled]

    def disable(self, name: str) -> bool:
        spec = self.get(name)
        if spec is None:
            return False
        self._tools[name] = replace(spec, enabled=False)
        return True

    def enable(self, name: str) -> bool:
        spec = self.get(name)
        if spec is None:
            return False
        self._tools[name] = replace(spec, enabled=True)
        return True


def build_core_tool_registry() -> ToolRegistry:
    """Build metadata for the built-in tools used by the optimizer."""
    registry = ToolRegistry()
    registry.register_many(
        [
            ToolSpec(
                name="build_check",
                description="Run the project build command from the project profile",
                entrypoint="nodes.test:_run_build_check",
                inputs=["project_path", "profile", "timeout"],
                outputs=["passed", "output", "skipped"],
                safety_level="medium",
            ),
            ToolSpec(
                name="test_check",
                description="Run the project test command from the project profile",
                entrypoint="nodes.test:_run_test_check",
                inputs=["project_path", "profile", "timeout"],
                outputs=["passed", "output", "skipped"],
                safety_level="medium",
            ),
            ToolSpec(
                name="ui_check",
                description="Run optional Playwright UI verification",
                entrypoint="nodes.test:_run_ui_check",
                inputs=["project_path", "profile", "timeout", "round_num"],
                outputs=["passed", "output", "skipped"],
                safety_level="medium",
            ),
            ToolSpec(
                name="context7_docs",
                description="Collect optional Context7 documentation grounding",
                entrypoint="utils.context7_client:collect_relevant_docs",
                inputs=["project_path", "plan", "profile"],
                outputs=["docs"],
                safety_level="low",
            ),
            ToolSpec(
                name="format_file",
                description="Run a detected or configured formatter for one file",
                entrypoint="utils.formatter:format_file",
                inputs=["formatter", "filepath", "project_path"],
                outputs=["passed", "output"],
                safety_level="medium",
            ),
        ]
    )
    return registry
