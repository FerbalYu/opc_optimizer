"""Tests for OptimizerStateModel Pydantic model."""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from state import OptimizerStateModel


class TestOptimizerStateModel:
    """Test OptimizerStateModel Pydantic validation."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        state = OptimizerStateModel()
        assert state.current_round == 1
        assert state.max_rounds == 5
        assert state.should_stop is False
        assert state.auto_mode is False
        assert state.dry_run is False
        assert state.run_mode == "legacy_mode"
        assert state.skill_name == "legacy_pipeline"
        assert state.router_decision == "legacy_linear"
        assert state.failure_type == "none"
        assert state.session_id == ""
        assert state.round_id == ""
        assert state.skill_preamble == ""

    def test_dict_access(self):
        """Test dictionary-style access."""
        state = OptimizerStateModel(project_path="/test")
        assert state["project_path"] == "/test"
        assert state.get("project_path") == "/test"
        assert state.get("nonexistent", "default") == "default"

    def test_dict_assignment(self):
        """Test dictionary-style assignment."""
        state = OptimizerStateModel()
        state["current_round"] = 5
        assert state.current_round == 5

    def test_complexity_validation(self):
        """Test task_complexity field validation."""
        state = OptimizerStateModel(task_complexity="low")
        assert state.task_complexity == "low"

        state = OptimizerStateModel(task_complexity="high")
        assert state.task_complexity == "high"

        # Invalid value should be normalized to "medium"
        state = OptimizerStateModel(task_complexity="invalid")
        assert state.task_complexity == "medium"

    def test_positive_int_validation(self):
        """Test that negative integers are converted to 0."""
        state = OptimizerStateModel(current_round=-5)
        assert state.current_round == 0

        state = OptimizerStateModel(max_rounds=-1)
        assert state.max_rounds == 0

    def test_run_mode_validation(self):
        """Test run mode normalization to supported values."""
        state = OptimizerStateModel(run_mode="skill_mode")
        assert state.run_mode == "skill_mode"

        state = OptimizerStateModel(run_mode="unexpected")
        assert state.run_mode == "legacy_mode"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        state = OptimizerStateModel(project_path="/test", optimization_goal="improve")
        d = state.to_dict()
        assert isinstance(d, dict)
        assert d["project_path"] == "/test"
        assert d["optimization_goal"] == "improve"

    def test_nested_fields(self):
        """Test nested dictionary fields."""
        state = OptimizerStateModel(
            llm_config={"model": "gpt-4"}, ui_preferences={"skip_plan_review": True}
        )
        assert state.llm_config["model"] == "gpt-4"
        assert state.ui_preferences["skip_plan_review"] is True

    def test_list_fields(self):
        """Test list fields."""
        state = OptimizerStateModel(
            modified_files=["a.py", "b.py"], execution_errors=["error 1"]
        )
        assert len(state.modified_files) == 2
        assert state.execution_errors[0] == "error 1"
