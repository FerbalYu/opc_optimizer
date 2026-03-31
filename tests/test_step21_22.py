import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.llm import _extract_first_json_object
from nodes.test import _evaluate_round_outcome, _collect_diff_evidence
from nodes.interact import interact_node


def _make_state(tmp_project, **overrides):
    state = {
        "project_path": str(tmp_project),
        "optimization_goal": "Improve code quality",
        "current_round": 1,
        "max_rounds": 5,
        "consecutive_no_improvements": 0,
        "suggestions": "",
        "current_plan": "",
        "round_contract": {},
        "round_evaluation": {},
        "code_diff": "",
        "test_results": "",
        "build_result": {},
        "should_stop": False,
        "round_reports": [],
        "execution_errors": [],
        "modified_files": [],
        "auto_mode": True,
        "dry_run": False,
        "archive_every_n_rounds": 3,
    }
    state.update(overrides)
    return state


class TestJsonExtraction:
    def test_extracts_json_from_preface_and_fence(self):
        raw = """Let me inspect the files first.

```json
{"round_objective":"Fix bug","target_files":["main.py"]}
```"""
        parsed = _extract_first_json_object(raw)
        assert parsed["round_objective"] == "Fix bug"
        assert parsed["target_files"] == ["main.py"]


class TestRoundEvaluation:
    def test_collects_real_diff_evidence_from_backup(self, tmp_project):
        file_path = tmp_project / "main.py"
        bak_path = tmp_project / "main.py.bak"
        bak_path.write_text("def hello():\n    print('hello')\n", encoding="utf-8")
        file_path.write_text("def hello_world():\n    print('hello')\n", encoding="utf-8")

        diff_text = _collect_diff_evidence(str(tmp_project), ["main.py"])

        assert "a/main.py" in diff_text
        assert "b/main.py" in diff_text
        assert "hello_world" in diff_text

    def test_marks_aligned_round_complete(self, tmp_project):
        state = _make_state(
            tmp_project,
            round_contract={
                "target_files": ["main.py"],
                "acceptance_checks": ["main.py should be modified"],
                "expected_diff": ["In main.py: Rename hello to hello_world"],
                "impact_score": 8,
                "confidence_score": 8,
                "verification_score": 7,
            },
            modified_files=["main.py"],
            code_diff="MODIFIED main.py: Rename hello to hello_world",
        )

        result = _evaluate_round_outcome(state, build_passed=True)

        assert result["objective_completed"] is True
        assert result["aligned_with_plan"] is True
        assert result["low_value_round"] is False
        assert result["replan_required"] is False

    def test_marks_low_value_when_expected_file_not_hit(self, tmp_project):
        state = _make_state(
            tmp_project,
            round_contract={
                "target_files": ["main.py", "utils.py"],
                "acceptance_checks": ["utils.py should be improved"],
                "expected_diff": ["In utils.py: Add validation"],
                "impact_score": 8,
                "confidence_score": 8,
                "verification_score": 7,
            },
            modified_files=["main.py"],
            code_diff="MODIFIED main.py: Rename hello to hello_world",
        )

        result = _evaluate_round_outcome(state, build_passed=True)

        assert result["objective_completed"] is False
        assert result["aligned_with_plan"] is False
        assert result["low_value_round"] is True
        assert result["replan_required"] is True
        assert "expected diff paths" in " ".join(result["reasons"])


class TestInteractNode:
    def test_auto_mode_continues_with_replan_signal(self, tmp_project):
        state = _make_state(
            tmp_project,
            auto_mode=True,
            round_evaluation={
                "low_value_round": True,
                "replan_required": True,
                "reasons": ["Modified files did not match expected diff paths."],
            },
            code_diff="MODIFIED main.py: Rename hello",
            modified_files=["main.py"],
        )

        result = interact_node(state)

        assert result["should_stop"] is False
        assert result["current_round"] == 2
        assert result["consecutive_no_improvements"] == 1
