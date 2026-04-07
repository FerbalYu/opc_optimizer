"""Skill input/output contract definitions and validators."""

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class SkillIOContract:
    name: str
    required_inputs: List[str]
    expected_outputs: List[str]


BASE_SKILL_CONTRACTS: Dict[str, SkillIOContract] = {
    "plan": SkillIOContract(
        name="plan",
        required_inputs=["project_path", "optimization_goal", "current_round"],
        expected_outputs=["current_plan", "round_contract"],
    ),
    "execute": SkillIOContract(
        name="execute",
        required_inputs=["project_path", "current_plan"],
        expected_outputs=["code_diff", "modified_files"],
    ),
    "test": SkillIOContract(
        name="test",
        required_inputs=["project_path", "code_diff"],
        expected_outputs=["test_results", "build_result", "round_evaluation"],
    ),
    "interact": SkillIOContract(
        name="interact",
        required_inputs=["current_round", "max_rounds"],
        expected_outputs=["should_stop", "current_round"],
    ),
    "report": SkillIOContract(
        name="report",
        required_inputs=["project_path", "current_round"],
        expected_outputs=["round_reports", "round_history"],
    ),
}


def get_skill_contract(skill_name: str) -> SkillIOContract:
    if skill_name not in BASE_SKILL_CONTRACTS:
        raise ValueError(f"No skill contract defined for: {skill_name}")
    return BASE_SKILL_CONTRACTS[skill_name]


def validate_skill_input(skill_name: str, state: dict) -> None:
    contract = get_skill_contract(skill_name)
    missing = [key for key in contract.required_inputs if key not in state]
    if missing:
        raise ValueError(
            f"Skill '{skill_name}' missing required inputs: {', '.join(missing)}"
        )


def validate_skill_output(skill_name: str, state: dict) -> None:
    contract = get_skill_contract(skill_name)
    missing = [key for key in contract.expected_outputs if key not in state]
    if missing:
        raise ValueError(
            f"Skill '{skill_name}' missing expected outputs: {', '.join(missing)}"
        )

