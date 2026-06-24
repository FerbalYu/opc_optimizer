import os
import sys
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import graph as graph_mod
from graph import (
    _build_skill_dispatcher,
    _first_skill_node,
    _route_after_archive,
    _route_after_execute,
    _route_after_interact,
    _route_after_plan,
    create_optimizer_graph,
    should_test,
)
from utils.skill_registry import SkillRegistry, SkillSpec


class TestGraphCompilation:
    """Verify the LangGraph can compile and has correct structure."""
    
    def test_graph_compiles(self):
        app = create_optimizer_graph()
        assert app is not None
    
    def test_graph_has_all_nodes(self):
        app = create_optimizer_graph()
        # The compiled graph should have the expected nodes
        graph = app.get_graph()
        node_ids = [n if isinstance(n, str) else getattr(n, 'id', str(n)) for n in graph.nodes]
        for expected in ["plan", "execute", "test", "archive", "report", "interact"]:
            assert expected in node_ids, f"Missing node: {expected}"

    def test_graph_wires_full_round_chain(self):
        app = create_optimizer_graph()
        edges = {
            (edge.source, edge.target, edge.conditional)
            for edge in app.get_graph().edges
        }

        assert ("task_router", "plan", True) in edges
        assert ("plan", "execute", True) in edges
        assert ("execute", "test", True) in edges
        assert ("execute", "archive", True) in edges
        assert ("test", "archive", False) in edges
        assert ("archive", "report", True) in edges
        assert ("report", "interact", True) in edges
        assert ("interact", "plan", True) in edges
        assert ("plan", "__end__", False) not in edges

    def test_graph_requires_core_skill_registration(self):
        registry = SkillRegistry()
        registry.register(
            SkillSpec(
                name="plan",
                description="plan",
                entrypoint="nodes.plan:plan_node",
            )
        )
        # Missing execute/test/report should fail graph construction
        with pytest.raises(ValueError):
            create_optimizer_graph(skill_registry=registry)


class TestMockLLMService:
    """Test the MockLLMService itself."""
    
    def test_generate_returns_text(self):
        from utils.mock_llm import MockLLMService
        mock = MockLLMService(text_response="test plan")
        result = mock.generate([{"role": "user", "content": "make a plan"}])
        assert result == "test plan"
    
    def test_generate_json_returns_dict(self):
        from utils.mock_llm import MockLLMService
        mock = MockLLMService(json_response={"modifications": [{"filepath": "a.py"}]})
        result = mock.generate_json([{"role": "user", "content": "generate json"}])
        assert result["modifications"][0]["filepath"] == "a.py"
    
    def test_call_log_tracks_calls(self):
        from utils.mock_llm import MockLLMService
        mock = MockLLMService()
        mock.generate([{"role": "user", "content": "q1"}])
        mock.generate_json([{"role": "user", "content": "q2"}])
        assert len(mock.call_log) == 2
        assert mock.call_log[0]["method"] == "generate"
        assert mock.call_log[1]["method"] == "generate_json"
    
    def test_reset_clears_log(self):
        from utils.mock_llm import MockLLMService
        mock = MockLLMService()
        mock.generate([{"role": "user", "content": "q"}])
        mock.reset()
        assert len(mock.call_log) == 0


class TestSkillDispatcher:
    def test_dispatcher_uses_legacy_path_when_not_skill_mode(self):
        def legacy_fn(state):
            state["path"] = "legacy"
            return state

        dispatcher = _build_skill_dispatcher("plan", legacy_fn)
        state = {"run_mode": "legacy_mode"}
        result = dispatcher(state)
        assert result["path"] == "legacy"
        assert result["skill_name"] == "legacy_pipeline"

    def test_dispatcher_skill_mode_and_legacy_mode_are_comparable(self, monkeypatch):
        def legacy_fn(state):
            state["result_tag"] = "stable"
            return state

        def fake_run_skill(skill_name, state):
            state["skill_name"] = skill_name
            state["result_tag"] = "stable"
            return state

        monkeypatch.setattr("utils.skill_bridge.run_skill", fake_run_skill, raising=True)

        dispatcher = _build_skill_dispatcher("plan", legacy_fn)
        legacy_state = dispatcher({"run_mode": "legacy_mode"})
        skill_state = dispatcher({"run_mode": "skill_mode"})

        assert legacy_state["result_tag"] == skill_state["result_tag"] == "stable"
        assert skill_state["skill_name"] == "plan"

    def test_dispatcher_fallbacks_to_legacy_on_skill_error(self, monkeypatch):
        def legacy_fn(state):
            state["legacy_called"] = True
            return state

        def failing_run_skill(skill_name, state):
            raise RuntimeError("boom")

        monkeypatch.setattr("utils.skill_bridge.run_skill", failing_run_skill, raising=True)

        dispatcher = _build_skill_dispatcher("execute", legacy_fn)
        state = {"run_mode": "skill_mode", "failure_type": "none"}
        result = dispatcher(state)

        assert result["legacy_called"] is True
        assert result["run_mode"] == "legacy_mode"
        assert result["failure_type"] == "skill_dispatch_failed"
        assert result["fallback_reason"].startswith("skill_dispatch_failed:execute")
        assert "fallback_legacy" in result["router_decision"]


def test_should_test_respects_skill_chain_skip():
    state = {
        "run_mode": "skill_mode",
        "skill_chain": ["plan", "execute", "report"],
        "fast_path": False,
    }

    assert should_test(state) == "skip_test"


def test_skill_chain_routes_doc_only_path_through_archive():
    state = {
        "run_mode": "skill_mode",
        "skill_chain": ["plan", "execute", "report"],
        "fast_path": False,
    }

    assert _first_skill_node(state) == "plan"
    assert _route_after_plan(state) == "execute"
    assert _route_after_execute(state) == "archive"
    assert _route_after_archive(state) == "report"


def test_skill_chain_can_start_from_execute():
    state = {
        "run_mode": "skill_mode",
        "skill_chain": ["execute", "report"],
        "fast_path": False,
    }

    assert _first_skill_node(state) == "execute"
    assert _route_after_execute(state) == "archive"
    assert _route_after_archive(state) == "report"


def test_legacy_route_ignores_skill_chain_override():
    state = {
        "run_mode": "legacy_mode",
        "skill_chain": ["report"],
        "fast_path": False,
        "should_stop": False,
    }

    assert _first_skill_node(state) == "plan"
    assert _route_after_plan(state) == "execute"
    assert _route_after_execute(state) == "test"
    assert _route_after_archive(state) == "report"
    assert _route_after_interact(state) == "plan"
