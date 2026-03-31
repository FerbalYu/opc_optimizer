"""Tests for utils/context_pruner.py (v2.7.0)."""

import os
import sys
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.context_pruner import (
    condense_history,
    _format_detailed,
    _condense_mechanical,
)


def _make_history(n):
    """Generate n fake round history entries."""
    return [
        {
            "round": i + 1,
            "summary": f"Modified file_{i}.py: added error handling" * 3,
            "files_changed": [f"src/file_{i}.py", f"tests/test_{i}.py"],
            "suggestions": f"Consider refactoring module {i}",
        }
        for i in range(n)
    ]


class TestFormatDetailed:
    def test_empty(self):
        assert _format_detailed([]) == ""

    def test_single_round(self):
        result = _format_detailed(_make_history(1))
        assert "Round 1" in result
        assert "file_0.py" in result

    def test_multiple_rounds(self):
        result = _format_detailed(_make_history(3))
        assert "Round 1" in result
        assert "Round 3" in result


class TestCondenseMechanical:
    def test_empty(self):
        assert _condense_mechanical([]) == ""

    def test_basic(self):
        result = _condense_mechanical(_make_history(3))
        assert "R1:" in result
        assert "R3:" in result

    def test_truncation(self):
        """Summary should be truncated to 80 chars."""
        history = [{"round": 1, "summary": "x" * 200, "files_changed": ["a.py"]}]
        result = _condense_mechanical(history)
        # The 80-char summary + prefix "- R1: " + file info should be manageable
        assert len(result) < 200

    def test_many_files(self):
        """More than 3 files should show (+N)."""
        history = [{"round": 1, "summary": "test", "files_changed": ["a", "b", "c", "d", "e"]}]
        result = _condense_mechanical(history)
        assert "(+2)" in result


class TestCondenseHistory:
    def test_empty_history(self):
        assert condense_history([]) == ""

    def test_short_history_no_condensation(self):
        """≤ window_size rounds → returns full detail, no condensation."""
        history = _make_history(2)
        result = condense_history(history, llm=None, window_size=2)
        assert "Round 1" in result
        assert "Round 2" in result
        # Should NOT have "历史教训" section since no condensation needed
        assert "历史教训" not in result

    def test_long_history_mechanical_fallback(self):
        """Without LLM, older rounds use mechanical fallback."""
        history = _make_history(5)
        result = condense_history(history, llm=None, window_size=2)
        # Should have condensed section for older (rounds 1-3)
        assert "历史教训" in result
        # Should have recent detail (rounds 4-5)
        assert "近期轮次" in result
        assert "Round 4" in result
        assert "Round 5" in result

    def test_long_history_with_llm(self):
        """With LLM mock, older rounds get LLM-condensed."""
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "- 不要改 init_db\n- utils.py 重构已完成"

        history = _make_history(5)
        result = condense_history(history, llm=mock_llm, window_size=2)

        assert "历史教训" in result
        assert "不要改 init_db" in result
        assert "近期轮次" in result
        assert "Round 5" in result
        # LLM should have been called once
        mock_llm.generate.assert_called_once()

    def test_llm_failure_falls_back(self):
        """If LLM raises, should fall back to mechanical."""
        mock_llm = MagicMock()
        mock_llm.generate.side_effect = RuntimeError("API error")

        history = _make_history(5)
        result = condense_history(history, llm=mock_llm, window_size=2)
        # Should still produce output via mechanical fallback
        assert "历史教训" in result
        assert "R1:" in result  # mechanical format

    def test_window_size_custom(self):
        """Custom window_size keeps more recent rounds."""
        history = _make_history(6)
        result = condense_history(history, llm=None, window_size=3)
        # Recent 3 should be detailed
        assert "Round 4" in result
        assert "Round 5" in result
        assert "Round 6" in result

    def test_result_is_string(self):
        """Output should always be a string."""
        for n in [0, 1, 2, 5, 10]:
            result = condense_history(_make_history(n), llm=None)
            assert isinstance(result, str)

    def test_condensed_shorter_than_raw(self):
        """For many rounds, condensed output should be shorter than raw."""
        history = _make_history(10)
        raw = _format_detailed(history)
        condensed = condense_history(history, llm=None, window_size=2)
        # Condensed should be significantly shorter
        assert len(condensed) < len(raw)
