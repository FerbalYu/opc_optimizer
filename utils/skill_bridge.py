"""Skill bridge wrappers for existing workflow nodes.

Phase 3 / P3-1 goal:
- Keep legacy node algorithms unchanged.
- Provide skillized entrypoints with a unified invocation interface.
"""

from typing import Callable, Dict, List

SkillHandler = Callable[[dict], dict]
BASE_SKILL_ORDER = ["plan", "execute", "test", "interact", "report"]


def _load_node_handlers() -> Dict[str, SkillHandler]:
    """Load baseline node callables as skill handlers."""
    try:
        from nodes.plan import plan_node
        from nodes.execute import execute_node
        from nodes.test import test_node
        from nodes.interact import interact_node
        from nodes.report import report_node
    except ImportError:
        from ..nodes.plan import plan_node
        from ..nodes.execute import execute_node
        from ..nodes.test import test_node
        from ..nodes.interact import interact_node
        from ..nodes.report import report_node

    return {
        "plan": plan_node,
        "execute": execute_node,
        "test": test_node,
        "interact": interact_node,
        "report": report_node,
    }


def get_base_skill_handlers() -> Dict[str, SkillHandler]:
    """Expose base skill handlers for bridge/runtime use."""
    return _load_node_handlers()


def build_base_skill_plan() -> List[str]:
    """Return the baseline skill chain order."""
    return list(BASE_SKILL_ORDER)


def run_skill(
    skill_name: str,
    state: dict,
    handlers: Dict[str, SkillHandler] | None = None,
) -> dict:
    """Run one bridged skill by name and return updated state."""
    try:
        from utils.skill_contract import validate_skill_input, validate_skill_output
    except ImportError:
        from .skill_contract import validate_skill_input, validate_skill_output

    active_handlers = handlers or get_base_skill_handlers()
    if skill_name not in active_handlers:
        raise ValueError(f"Unsupported skill name: {skill_name}")

    validate_skill_input(skill_name, state)
    state["skill_name"] = skill_name
    output_state = active_handlers[skill_name](state)
    validate_skill_output(skill_name, output_state)
    return output_state
