"""Tests for utils/metrics_tracker.py — autoresearch-inspired metrics collection."""

import os
import sys
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.metrics_tracker import collect_round_metrics, append_metrics, load_metrics, _count_diff_lines


def _make_state(tmp_path, **overrides):
    state = {
        "project_path": str(tmp_path),
        "optimization_goal": "Improve code quality",
        "current_round": 1,
        "max_rounds": 5,
        "consecutive_no_improvements": 0,
        "suggestions": "",
        "current_plan": "",
        "round_contract": {},
        "round_evaluation": {"value_score": 7, "low_value_round": False},
        "code_diff": "",
        "test_results": "",
        "build_result": {"build_passed": True, "test_passed": True},
        "should_stop": False,
        "round_reports": [],
        "execution_errors": [],
        "modified_files": [],
        "auto_mode": True,
        "dry_run": False,
        "archive_every_n_rounds": 3,
        "node_timings": {"plan": 5.2, "execute": 12.3, "test": 8.1},
        "round_start_time": time.time() - 30,  # 30 seconds ago
    }
    state.update(overrides)
    return state


class TestCollectRoundMetrics:
    def test_basic_fields(self, tmp_project):
        state = _make_state(tmp_project)
        metrics = collect_round_metrics(state)

        assert metrics["round"] == 1
        assert "timestamp" in metrics
        assert metrics["skill_name"] == "legacy_pipeline"
        assert metrics["router_decision"] == "legacy_linear"
        assert metrics["failure_type"] == "none"
        assert metrics["value_score"] == 7
        assert metrics["build_passed"] is True
        assert metrics["test_passed"] is True
        assert metrics["files_changed_count"] == 0
        assert metrics["lines_added"] == 0
        assert metrics["lines_removed"] == 0
        assert metrics["net_lines_delta"] == 0
        assert metrics["round_elapsed_seconds"] > 0
        assert metrics["is_rollback"] is False

    def test_with_modified_files(self, tmp_project):
        (tmp_project / "main.py.bak").write_text("def hello():\n    print('hello')\n", encoding="utf-8")
        (tmp_project / "main.py").write_text("def hello_world():\n    print('hello world')\n", encoding="utf-8")

        state = _make_state(tmp_project, modified_files=["main.py"])
        metrics = collect_round_metrics(state)

        assert metrics["files_changed_count"] == 1
        assert metrics["lines_added"] > 0
        assert metrics["lines_removed"] > 0

    def test_rollback_flag_on_build_failure(self, tmp_project):
        state = _make_state(
            tmp_project,
            build_result={"build_passed": False, "test_passed": True},
        )
        metrics = collect_round_metrics(state)
        assert metrics["is_rollback"] is True
        assert metrics["failure_type"] == "build_failed"

    def test_failure_type_prefers_execution_errors(self, tmp_project):
        state = _make_state(
            tmp_project,
            execution_errors=["[execute] RuntimeError: failed"],
            build_result={"build_passed": False, "test_passed": False},
        )
        metrics = collect_round_metrics(state)
        assert metrics["failure_type"] == "node_error"

    def test_rollback_flag_on_low_value(self, tmp_project):
        state = _make_state(
            tmp_project,
            round_evaluation={"value_score": 3, "low_value_round": True},
        )
        metrics = collect_round_metrics(state)
        assert metrics["is_rollback"] is True

    def test_node_timings_recorded(self, tmp_project):
        state = _make_state(tmp_project)
        metrics = collect_round_metrics(state)
        assert metrics["total_node_time_seconds"] > 0
        assert "plan" in metrics["node_timings"]


class TestAppendAndLoadMetrics:
    def test_append_creates_file(self, tmp_project):
        (tmp_project / ".opclog").mkdir(exist_ok=True)
        metrics = {"round": 1, "value_score": 7}
        path = append_metrics(str(tmp_project), metrics)
        assert os.path.exists(path)

    def test_append_and_load_roundtrip(self, tmp_project):
        (tmp_project / ".opclog").mkdir(exist_ok=True)
        project_path = str(tmp_project)

        for i in range(3):
            append_metrics(project_path, {"round": i + 1, "value_score": 5 + i})

        rows = load_metrics(project_path)
        assert len(rows) == 3
        assert rows[0]["round"] == 1
        assert rows[0]["value_score"] == 5
        assert rows[2]["round"] == 3
        assert rows[2]["value_score"] == 7

    def test_load_returns_empty_if_no_file(self, tmp_project):
        rows = load_metrics(str(tmp_project))
        assert rows == []

    def test_load_skips_malformed_lines(self, tmp_project):
        (tmp_project / ".opclog").mkdir(exist_ok=True)
        metrics_file = tmp_project / ".opclog" / "metrics.jsonl"
        metrics_file.write_text(
            '{"round": 1, "value_score": 5}\n'
            'not valid json\n'
            '{"round": 2, "value_score": 8}\n',
            encoding="utf-8",
        )
        rows = load_metrics(str(tmp_project))
        assert len(rows) == 2


class TestDiffLineCounting:
    def test_counts_added_and_removed(self, tmp_project):
        (tmp_project / "a.py.bak").write_text("line1\nline2\nline3\n", encoding="utf-8")
        (tmp_project / "a.py").write_text("line1\nline2_modified\nline3\nline4\n", encoding="utf-8")

        counts = _count_diff_lines(str(tmp_project), ["a.py"])
        assert counts["lines_added"] >= 1  # line2_modified + line4
        assert counts["lines_removed"] >= 1  # line2
        assert counts["net_lines_delta"] == counts["lines_added"] - counts["lines_removed"]

    def test_no_bak_gives_zero(self, tmp_project):
        counts = _count_diff_lines(str(tmp_project), ["nonexistent.py"])
        assert counts["lines_added"] == 0
        assert counts["lines_removed"] == 0
