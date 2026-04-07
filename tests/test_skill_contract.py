"""Tests for `utils.skill_contract`."""

import pytest

from utils.skill_contract import get_skill_contract, validate_skill_input, validate_skill_output


def test_get_skill_contract_plan():
    contract = get_skill_contract("plan")
    assert contract.name == "plan"
    assert "project_path" in contract.required_inputs
    assert "current_plan" in contract.expected_outputs


def test_validate_skill_input_missing_keys_raises():
    with pytest.raises(ValueError):
        validate_skill_input("execute", {"project_path": "/tmp"})


def test_validate_skill_output_missing_keys_raises():
    with pytest.raises(ValueError):
        validate_skill_output("test", {"test_results": "ok"})


def test_get_skill_contract_unknown_raises():
    with pytest.raises(ValueError):
        get_skill_contract("unknown_skill")
