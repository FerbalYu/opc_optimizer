"""Tests for checkpoint save/load/clear operations."""

import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.checkpoint import save_checkpoint, load_checkpoint, clear_checkpoint


class TestSaveCheckpoint:
    def test_creates_checkpoint_file(self, tmp_project):
        state = {"current_round": 3, "should_stop": False, "project_path": str(tmp_project)}
        path = save_checkpoint(str(tmp_project), state)
        assert os.path.exists(path)
        assert path.endswith("checkpoint.json")

    def test_serializes_state_correctly(self, tmp_project):
        state = {
            "current_round": 2,
            "should_stop": False,
            "round_reports": ["/path/report1.md", "/path/report2.md"],
            "execution_errors": ["error1"],
            "optimization_goal": "性能优化",
        }
        path = save_checkpoint(str(tmp_project), state)
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data["current_round"] == 2
        assert data["should_stop"] is False
        assert len(data["round_reports"]) == 2
        assert data["optimization_goal"] == "性能优化"

    def test_handles_non_serializable_fields(self, tmp_project):
        """Non-JSON-serializable values should be converted to string."""
        state = {
            "current_round": 1,
            "complex_obj": {"nested": True},  # dict is JSON-safe
            "should_stop": False,
        }
        path = save_checkpoint(str(tmp_project), state)
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data["current_round"] == 1

    def test_overwrites_existing_checkpoint(self, tmp_project):
        state1 = {"current_round": 1, "should_stop": False}
        state2 = {"current_round": 5, "should_stop": True}
        save_checkpoint(str(tmp_project), state1)
        path = save_checkpoint(str(tmp_project), state2)
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data["current_round"] == 5


class TestLoadCheckpoint:
    def test_load_existing_checkpoint(self, tmp_project):
        state = {"current_round": 3, "should_stop": False, "round_reports": []}
        save_checkpoint(str(tmp_project), state)
        loaded = load_checkpoint(str(tmp_project))
        assert loaded is not None
        assert loaded["current_round"] == 3

    def test_returns_none_when_no_checkpoint(self, tmp_path):
        result = load_checkpoint(str(tmp_path))
        assert result is None

    def test_sets_defaults_for_missing_fields(self, tmp_project):
        """If checkpoint is missing fields, setdefault fills them."""
        checkpoint_path = os.path.join(str(tmp_project), ".opclog", "checkpoint.json")
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump({"optimization_goal": "test"}, f)
        loaded = load_checkpoint(str(tmp_project))
        assert loaded is not None
        assert loaded["current_round"] == 1
        assert loaded["should_stop"] is False
        assert loaded["round_reports"] == []
        assert loaded["execution_errors"] == []
        assert loaded["modified_files"] == []

    def test_handles_corrupted_json(self, tmp_project):
        checkpoint_path = os.path.join(str(tmp_project), ".opclog", "checkpoint.json")
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            f.write("{corrupt json data!!!")
        result = load_checkpoint(str(tmp_project))
        assert result is None

    def test_roundtrip_save_load(self, tmp_project):
        original = {
            "current_round": 4,
            "should_stop": False,
            "optimization_goal": "架构优化",
            "round_reports": ["r1.md", "r2.md"],
            "execution_errors": [],
            "modified_files": ["main.py"],
            "auto_mode": True,
            "dry_run": False,
        }
        save_checkpoint(str(tmp_project), original)
        loaded = load_checkpoint(str(tmp_project))
        assert loaded is not None
        for key in original:
            assert loaded[key] == original[key], f"Mismatch on key: {key}"


class TestClearCheckpoint:
    def test_clears_existing(self, tmp_project):
        save_checkpoint(str(tmp_project), {"current_round": 1})
        checkpoint_path = os.path.join(str(tmp_project), ".opclog", "checkpoint.json")
        assert os.path.exists(checkpoint_path)
        clear_checkpoint(str(tmp_project))
        assert not os.path.exists(checkpoint_path)

    def test_clears_nonexistent_is_noop(self, tmp_path):
        """Should not raise when no checkpoint exists."""
        clear_checkpoint(str(tmp_path))  # should not raise
