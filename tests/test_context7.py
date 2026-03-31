"""Tests for Step 17 Context7 docs grounding."""

import os
import sys
import json
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.context7_client import (
    collect_relevant_docs,
    guess_libraries,
    is_context7_enabled,
    query_docs,
)
from utils.mock_llm import MockLLMService


class FakeContext7Client:
    def __init__(self):
        self.calls = []

    def query_docs(self, library, query):
        self.calls.append((library, query))
        return f"Resolved `{library}`\n- Use current APIs only"


class TestContext7Config:
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            assert is_context7_enabled() is False

    def test_enabled_with_required_env(self):
        with patch.dict(
            os.environ,
            {
                "OPC_ENABLE_CONTEXT7": "true",
                "CONTEXT7_SERVER_URL": "https://example.test/mcp",
                "OPENAI_API_KEY": "sk-test",
            },
            clear=False,
        ):
            assert is_context7_enabled() is True


class TestGuessLibraries:
    def test_uses_profile_hint_for_vue(self, tmp_path):
        libs = guess_libraries(str(tmp_path), "Refactor component state management", profile={"type": "vue"})
        assert "vue" in libs

    def test_detects_from_package_json(self, tmp_path):
        with open(tmp_path / "package.json", "w", encoding="utf-8") as f:
            json.dump({"dependencies": {"next": "14.0.0", "react": "18.0.0"}}, f)
        libs = guess_libraries(str(tmp_path), "Fix router usage", profile={"type": "javascript"})
        assert "next.js" in libs
        assert "react" in libs

    def test_detects_from_python_requirements(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("fastapi\npydantic\n", encoding="utf-8")
        libs = guess_libraries(str(tmp_path), "Adjust request validation", profile={"type": "python"})
        assert "fastapi" in libs
        assert "pydantic" in libs

    def test_uses_plan_keywords(self, tmp_path):
        libs = guess_libraries(str(tmp_path), "Migrate Vue watchers to computed", profile={})
        assert "vue" in libs


class TestQueryDocs:
    def test_uses_injected_client(self):
        client = FakeContext7Client()
        result = query_docs("vue", "reactive vs ref", client=client)
        assert "Resolved `vue`" in result
        assert client.calls == [("vue", "reactive vs ref")]

    def test_client_failure_falls_back_to_empty(self):
        class BrokenClient:
            def query_docs(self, library, query):
                raise RuntimeError("boom")

        result = query_docs("vue", "reactive vs ref", client=BrokenClient())
        assert result == ""


class TestCollectRelevantDocs:
    def test_combines_multiple_doc_sections(self, tmp_path):
        with open(tmp_path / "package.json", "w", encoding="utf-8") as f:
            json.dump({"dependencies": {"vue": "3.4.0", "vite": "5.0.0"}}, f)

        client = FakeContext7Client()
        docs = collect_relevant_docs(
            str(tmp_path),
            "Update Vue component and Vite config",
            profile={"type": "vue"},
            client=client,
            max_docs=2,
        )
        assert "## Relevant framework/library docs" in docs
        assert "### vue" in docs.lower()
        assert len(client.calls) >= 1


class TestExecuteIntegration:
    @patch("utils.diff_parser.parse_llm_output", return_value=[])
    @patch("nodes.execute._build_doc_context", return_value="## Relevant framework/library docs (Context7)\n\n### vue\nUse ref() correctly.")
    @patch("nodes.execute._build_smart_context", return_value="### src/App.vue\n```vue\nconst x = 1\n```")
    @patch("nodes.execute.LLMService")
    def test_execute_prompt_includes_doc_context(self, MockLLM, _smart, _docs, _parse, tmp_project):
        mock_instance = MockLLMService(text_response="No changes")
        MockLLM.return_value = mock_instance
        MockLLM.truncate_to_budget = staticmethod(lambda text, budget, label="": text)

        from nodes.execute import execute_node

        state = {
            "project_path": str(tmp_project),
            "optimization_goal": "Improve code quality",
            "current_round": 1,
            "max_rounds": 5,
            "consecutive_no_improvements": 0,
            "suggestions": "",
            "current_plan": "Update Vue reactivity usage in src/App.vue",
            "code_diff": "",
            "test_results": "",
            "should_stop": False,
            "round_reports": [],
            "execution_errors": [],
            "modified_files": [],
            "auto_mode": True,
            "dry_run": False,
            "archive_every_n_rounds": 3,
            "llm_config": {},
        }

        result = execute_node(state)
        assert result["code_diff"] == "No changes parsed from LLM output."
        prompt = mock_instance.call_log[0]["messages"][1]["content"]
        assert "Relevant framework/library docs grounding" in prompt
        assert "Use ref() correctly." in prompt
