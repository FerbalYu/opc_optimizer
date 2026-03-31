"""Tests for Step 4 features: sandbox execution, token cost, plugin system."""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nodes.execute import _apply_modification
from utils.llm import LLMService
from plugins import BaseNode, load_plugins, discover_plugins


class TestSandboxExecution:
    """4.1 — Modifications go through temp-dir sandbox with verification."""

    def test_blocks_python_syntax_error(self, tmp_project):
        """If LLM produces invalid Python, sandbox compile() catches it."""
        mod = {
            "filepath": "main.py",
            "old_content_snippet": "def hello():",
            "new_content": "def hello(\n    # missing closing paren",
            "reason": "optimization"
        }
        result = _apply_modification(str(tmp_project), mod)
        assert result.startswith("BLOCKED")
        assert "sandbox compilation failed" in result
        # Original file should be unchanged
        with open(tmp_project / "main.py", 'r', encoding='utf-8') as f:
            assert "def hello():" in f.read()

    def test_allows_valid_python(self, tmp_project):
        mod = {
            "filepath": "main.py",
            "old_content_snippet": "def hello():",
            "new_content": "def greet(name: str):",
            "reason": "add type hint"
        }
        result = _apply_modification(str(tmp_project), mod)
        assert result.startswith("MODIFIED")
        with open(tmp_project / "main.py", 'r', encoding='utf-8') as f:
            assert "def greet(name: str):" in f.read()

    def test_non_python_skips_compilation(self, tmp_project):
        """Non-.py files skip the compile step."""
        # Create a JS file
        js_path = tmp_project / "app.js"
        js_path.write_text("const x = 1;\n", encoding='utf-8')
        mod = {
            "filepath": "app.js",
            "old_content_snippet": "const x = 1;",
            "new_content": "const x = 42;",
            "reason": "update value"
        }
        result = _apply_modification(str(tmp_project), mod)
        assert result.startswith("MODIFIED")

    def test_backup_created_on_modify(self, tmp_project):
        mod = {
            "filepath": "main.py",
            "old_content_snippet": "def hello():",
            "new_content": "def goodbye():",
            "reason": "rename"
        }
        _apply_modification(str(tmp_project), mod)
        assert os.path.exists(str(tmp_project / "main.py.bak"))


class TestTokenCostTracking:
    """4.3 — Token cost calculation with pricing table."""

    def test_calculate_cost_gpt4o(self):
        # Use a non-default model name so DEFAULT_LLM_MODEL env doesn't override it
        llm = LLMService(model_name="gpt-4o")
        # gpt-4o: $2.50/1M input, $10.00/1M output
        cost = llm._calculate_cost(1000, 500)
        expected = (1000 * 2.50 + 500 * 10.00) / 1_000_000  # = 0.0075
        assert abs(cost - expected) < 0.001

    def test_calculate_cost_gpt4o_mini(self):
        llm = LLMService(model_name="gpt-4o-mini")
        cost = llm._calculate_cost(1000, 500)
        expected = (1000 * 0.15 + 500 * 0.60) / 1_000_000
        assert abs(cost - expected) < 0.001

    def test_calculate_cost_unknown_model(self):
        llm = LLMService(model_name="unknown/model-xyz")
        cost = llm._calculate_cost(1000, 500)
        assert cost == 0.0

    def test_calculate_cost_zero_tokens(self):
        llm = LLMService(model_name="gpt-4o")
        cost = llm._calculate_cost(0, 0)
        assert cost == 0.0

    def test_pricing_table_has_entries(self):
        assert len(LLMService.MODEL_PRICING) >= 10


class TestPluginSystem:
    """4.4 — BaseNode interface and plugin loading."""

    def test_basenode_is_abstract(self):
        with pytest.raises(TypeError):
            BaseNode()  # Can't instantiate abstract class

    def test_custom_node_implementation(self):
        class MyNode(BaseNode):
            name = "custom"
            description = "A test node"
            insert_after = "test"
            
            def run(self, state):
                state["custom_result"] = "done"
                return state
        
        node = MyNode()
        assert node.name == "custom"
        state = {"custom_result": ""}
        result = node.run(state)
        assert result["custom_result"] == "done"

    def test_load_plugins_empty_dir(self, tmp_path):
        plugins = load_plugins(str(tmp_path))
        assert plugins == []

    def test_load_plugins_nonexistent_dir(self):
        plugins = load_plugins("/nonexistent/dir")
        assert plugins == []

    def test_load_plugins_with_plugin_file(self, tmp_path):
        plugin_code = '''
from plugins import BaseNode

class LintNode(BaseNode):
    name = "lint"
    description = "Run linting"
    
    def run(self, state):
        state["lint_passed"] = True
        return state
'''
        (tmp_path / "lint_node.py").write_text(plugin_code, encoding='utf-8')
        plugins = load_plugins(str(tmp_path))
        assert len(plugins) == 1
        assert plugins[0].name == "lint"
        # Test the plugin runs
        state = {}
        result = plugins[0].run(state)
        assert result["lint_passed"] is True

    def test_discover_plugins_no_dir(self, tmp_path):
        plugins = discover_plugins(str(tmp_path))
        assert plugins == []

    def test_load_plugins_skips_invalid(self, tmp_path):
        """Invalid Python files should be skipped without crashing."""
        (tmp_path / "bad.py").write_text("this is not valid python!!!{{{", encoding='utf-8')
        plugins = load_plugins(str(tmp_path))
        assert plugins == []

    def test_load_plugins_skips_underscore_files(self, tmp_path):
        (tmp_path / "__init__.py").write_text("# init", encoding='utf-8')
        (tmp_path / "_private.py").write_text("# private", encoding='utf-8')
        plugins = load_plugins(str(tmp_path))
        assert plugins == []
