"""Tests for Chinese-first user-visible LLM prompts and reports."""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.mock_llm import MockLLMService


def _make_state(tmp_project, **overrides):
    state = {
        "project_path": str(tmp_project),
        "optimization_goal": "修复 stats_tool.py 的测试失败，保持测试文件不变",
        "current_round": 1,
        "max_rounds": 5,
        "consecutive_no_improvements": 0,
        "suggestions": "",
        "current_plan": "",
        "round_contract": {},
        "code_diff": "",
        "test_results": "",
        "build_result": {},
        "round_evaluation": {},
        "should_stop": False,
        "round_reports": [],
        "execution_errors": [],
        "modified_files": [],
        "auto_mode": True,
        "dry_run": False,
        "archive_every_n_rounds": 3,
        "node_timings": {},
    }
    state.update(overrides)
    return state


def test_plan_prompt_requires_chinese_user_visible_json(tmp_project):
    mock_instance = MockLLMService(
        json_response={
            "round_objective": "修复 main.py 中的问题",
            "current_state_assessment": "当前实现存在失败用例。",
            "product_manager_summary": "提升工具稳定性。",
            "target_files": ["main.py"],
            "acceptance_checks": ["python -m pytest -q 通过"],
            "expected_diff": ["main.py: 修复失败逻辑"],
            "risk_level": "low",
            "fallback_if_blocked": "缩小为最小修复。",
            "impact_score": 7,
            "confidence_score": 8,
            "verification_score": 8,
            "effort_score": 2,
        }
    )

    with patch("nodes.plan.LLMService") as MockLLM:
        MockLLM.return_value = mock_instance
        MockLLM.truncate_to_budget = staticmethod(lambda text, budget, label="": text)
        MockLLM.estimate_tokens = staticmethod(lambda text: len(text) // 4)

        from nodes.plan import plan_node

        plan_node(_make_state(tmp_project))

    system_prompt = mock_instance.call_log[0]["messages"][0]["content"]
    user_prompt = mock_instance.call_log[0]["messages"][1]["content"]
    assert "Human-readable JSON string values must use Simplified Chinese" in system_prompt
    assert "面向用户阅读的内容必须使用简体中文" in user_prompt
    assert "测试文件不变" in user_prompt


def test_execute_prompt_keeps_protocol_english_but_reason_chinese(tmp_project, monkeypatch):
    (tmp_project / "dummy.py").write_text("foo\n", encoding="utf-8")

    mock_instance = MockLLMService(
        text_response="\n".join([
            "dummy.py",
            "<<<<<<< SEARCH",
            "foo",
            "=======",
            "bar",
            ">>>>>>> REPLACE",
        ])
    )

    from nodes.execute import execute_node

    with patch("nodes.execute.LLMService") as MockLLM:
        MockLLM.return_value = mock_instance
        MockLLM.truncate_to_budget = staticmethod(lambda text, budget, label="": text)
        MockLLM.estimate_tokens = staticmethod(lambda text: len(text) // 4)
        execute_node(
            _make_state(
                tmp_project,
                current_plan="修复 dummy.py",
                round_contract={
                    "target_files": ["dummy.py"],
                    "acceptance_checks": ["python -m pytest -q"],
                    "expected_diff": ["dummy.py: 修复 foo"],
                },
            )
        )

    prompt = mock_instance.call_log[0]["messages"][1]["content"]
    assert "面向用户阅读的内容必须使用简体中文" in prompt
    assert "SEARCH/REPLACE" in prompt
    assert "Human-readable `reason` values" in prompt


def test_review_prompt_requires_chinese_markdown(tmp_project, monkeypatch):
    mock_instance = MockLLMService(text_response="## 优化建议\n- 继续修复。")

    from nodes.test import test_node

    with patch("nodes.test.LLMService") as MockLLM, patch(
        "utils.project_profile.load_project_profile",
        return_value={"type": "python", "build_cmd": None, "test_cmd": None},
    ), patch(
        "nodes.test._detect_and_run_build",
        return_value="No build command configured — skipped.",
    ), patch(
        "nodes.test._run_test_check",
        return_value={"passed": True, "output": "No test command configured — skipped.", "skipped": True},
    ), patch(
        "nodes.test._run_ui_check",
        return_value={"passed": True, "output": "UI verification disabled - skipped.", "skipped": True},
    ):
        MockLLM.return_value = mock_instance
        test_node(_make_state(tmp_project, code_diff="MODIFIED main.py: 修复"))

    system_prompt = mock_instance.call_log[0]["messages"][0]["content"]
    user_prompt = mock_instance.call_log[0]["messages"][1]["content"]
    assert "Use Simplified Chinese markdown" in system_prompt
    assert "Format your output as markdown in Simplified Chinese" in user_prompt
    assert "需要重新规划" in user_prompt


def test_report_markdown_uses_chinese_headings(tmp_project):
    from nodes.report import report_node

    state = _make_state(
        tmp_project,
        current_plan="# 第 1 轮计划合约\n",
        code_diff="MODIFIED main.py: 修复",
        test_results="ok",
        modified_files=["main.py"],
        round_evaluation={"low_value_round": False, "value_score": 9},
        suggestions="## 优化建议\n- 已完成。",
    )

    with patch("nodes.report.git_auto_commit"), patch("utils.checkpoint.save_checkpoint"):
        result = report_node(state)

    report_path = result["round_reports"][0]
    content = open(report_path, "r", encoding="utf-8").read()
    assert "# OPC 第 1 轮报告" in content
    assert "## 优化目标" in content
    assert "## 下一轮建议" in content
