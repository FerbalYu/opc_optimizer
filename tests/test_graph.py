import os
import sys
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from graph import create_optimizer_graph


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
