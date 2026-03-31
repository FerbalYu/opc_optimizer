"""Tests for Step 8 — diff_parser module (SEARCH/REPLACE + fuzzy matching)."""

import pytest
from utils.diff_parser import (
    parse_search_replace,
    parse_json_fallback,
    parse_llm_output,
    fuzzy_find_and_replace,
    generate_diff_preview,
)


class TestParseSearchReplace:
    def test_single_block(self):
        text = """Here's the change:

src/main.py
<<<<<<< SEARCH
def hello():
    print("old")
=======
def hello():
    print("new")
>>>>>>> REPLACE
"""
        mods = parse_search_replace(text)
        assert len(mods) == 1
        assert mods[0]["filepath"] == "src/main.py"
        assert 'print("old")' in mods[0]["old_content_snippet"]
        assert 'print("new")' in mods[0]["new_content"]

    def test_multiple_blocks(self):
        text = """
src/a.py
<<<<<<< SEARCH
x = 1
=======
x = 2
>>>>>>> REPLACE

src/b.py
<<<<<<< SEARCH
y = 10
=======
y = 20
>>>>>>> REPLACE
"""
        mods = parse_search_replace(text)
        assert len(mods) == 2
        assert mods[0]["filepath"] == "src/a.py"
        assert mods[1]["filepath"] == "src/b.py"

    def test_no_blocks(self):
        text = "Just some regular text without any SEARCH/REPLACE blocks."
        mods = parse_search_replace(text)
        assert len(mods) == 0

    def test_backtick_filepath(self):
        text = """
`utils/helper.py`
<<<<<<< SEARCH
old_code
=======
new_code
>>>>>>> REPLACE
"""
        mods = parse_search_replace(text)
        assert len(mods) == 1
        assert mods[0]["filepath"] == "utils/helper.py"


class TestParseJsonFallback:
    def test_valid_json(self):
        text = '{"modifications": [{"filepath": "a.py", "old_content_snippet": "x=1", "new_content": "x=2", "reason": "test"}]}'
        mods = parse_json_fallback(text)
        assert len(mods) == 1
        assert mods[0]["filepath"] == "a.py"

    def test_json_in_code_block(self):
        text = '''Some text
```json
{"modifications": [{"filepath": "b.py", "old_content_snippet": "y", "new_content": "z", "reason": "r"}]}
```
'''
        mods = parse_json_fallback(text)
        assert len(mods) == 1

    def test_invalid_json(self):
        text = "not json at all"
        mods = parse_json_fallback(text)
        assert len(mods) == 0


class TestParseLLMOutput:
    def test_prefers_search_replace(self):
        text = """
src/main.py
<<<<<<< SEARCH
old
=======
new
>>>>>>> REPLACE
"""
        mods = parse_llm_output(text)
        assert len(mods) == 1
        assert mods[0]["filepath"] == "src/main.py"

    def test_falls_back_to_json(self):
        text = '{"modifications": [{"filepath": "a.py", "old_content_snippet": "x", "new_content": "y", "reason": "z"}]}'
        mods = parse_llm_output(text)
        assert len(mods) == 1


class TestFuzzyFindAndReplace:
    def test_exact_match(self):
        content = "def hello():\n    print('hi')\n"
        search = "def hello():\n    print('hi')"
        replace = "def hello():\n    print('hello')"
        patched, ratio, status = fuzzy_find_and_replace(content, search, replace)
        assert status == "exact"
        assert ratio == 1.0
        assert "print('hello')" in patched

    def test_fuzzy_auto_match(self):
        content = "def hello():\n    print('hi')\n    return True\n"
        # Slightly different (extra space)
        search = "def hello():\n    print('hi') \n    return True"
        replace = "def hello_world():\n    print('hi')\n    return True"
        patched, ratio, status = fuzzy_find_and_replace(content, search, replace)
        assert status in ("auto_fuzzy", "exact")
        assert ratio > 0.85

    def test_no_match(self):
        content = "completely different code\nnothing similar\n"
        search = "def hello():\n    print('hi')"
        replace = "def hello_world():\n    print('hi')"
        patched, ratio, status = fuzzy_find_and_replace(content, search, replace)
        assert status == "rejected"
        assert patched is None

    def test_empty_inputs(self):
        patched, ratio, status = fuzzy_find_and_replace("", "search", "replace")
        assert status == "rejected"


class TestGenerateDiffPreview:
    def test_produces_diff(self):
        original = "line1\nline2\nline3\n"
        patched = "line1\nmodified\nline3\n"
        diff = generate_diff_preview("test.py", original, patched)
        assert "---" in diff
        assert "+++" in diff
        assert "-line2" in diff
        assert "+modified" in diff


class TestFilepathSanitization:
    """Tests for the _sanitize_filepath function added to reject LLM artifacts."""
    
    def test_rejects_html_tag_filepath(self):
        """MiniMax outputs <filepath> as a placeholder — should be rejected."""
        text = """
<filepath>
<<<<<<< SEARCH
old code
=======
new code
>>>>>>> REPLACE
"""
        mods = parse_search_replace(text)
        assert len(mods) == 0

    def test_rejects_think_tag_filepath(self):
        """MiniMax leaks </think> tags — should not become filenames."""
        text = """
</think>
<<<<<<< SEARCH
old
=======
new
>>>>>>> REPLACE
"""
        mods = parse_search_replace(text)
        assert len(mods) == 0

    def test_rejects_minimax_tool_call(self):
        """MiniMax leaks <minimax:tool_call> markers."""
        text = """
<minimax:tool_call>
<<<<<<< SEARCH
x = 1
=======
x = 2
>>>>>>> REPLACE
"""
        mods = parse_search_replace(text)
        assert len(mods) == 0

    def test_strips_markdown_bold_from_filepath(self):
        """Paths wrapped in **bold** should be cleaned, not rejected."""
        text = """
**utils/flying-stars.js**
<<<<<<< SEARCH
old_code()
=======
new_code()
>>>>>>> REPLACE
"""
        mods = parse_search_replace(text)
        assert len(mods) == 1
        assert mods[0]["filepath"] == "utils/flying-stars.js"

    def test_accepts_valid_filepath(self):
        """Normal file paths should still work."""
        text = """
src/utils/helper.py
<<<<<<< SEARCH
def old():
    pass
=======
def new():
    pass
>>>>>>> REPLACE
"""
        mods = parse_search_replace(text)
        assert len(mods) == 1
        assert mods[0]["filepath"] == "src/utils/helper.py"

    def test_rejects_bare_word_without_extension(self):
        """A bare word without slashes or dots is not a valid path."""
        text = """
filepath
<<<<<<< SEARCH
x
=======
y
>>>>>>> REPLACE
"""
        mods = parse_search_replace(text)
        assert len(mods) == 0

    def test_mixed_valid_and_invalid(self):
        """Only valid paths should be accepted in multi-block output."""
        text = """
<filepath>
<<<<<<< SEARCH
a
=======
b
>>>>>>> REPLACE

src/real-file.js
<<<<<<< SEARCH
c
=======
d
>>>>>>> REPLACE

</think>
<<<<<<< SEARCH
e
=======
f
>>>>>>> REPLACE
"""
        mods = parse_search_replace(text)
        assert len(mods) == 1
        assert mods[0]["filepath"] == "src/real-file.js"


class TestCleanLLMResponse:
    """Tests for the _clean_llm_response function in execute.py."""
    
    def test_removes_think_blocks(self):
        from nodes.execute import _clean_llm_response
        text = "Hello <think>internal reasoning</think> World"
        assert _clean_llm_response(text) == "Hello  World"

    def test_removes_orphaned_think_close(self):
        from nodes.execute import _clean_llm_response
        text = "Some output</think>rest of text"
        assert _clean_llm_response(text) == "Some outputrest of text"

    def test_removes_minimax_tool_call(self):
        from nodes.execute import _clean_llm_response
        text = "Code <minimax:tool_call>tool data</minimax:tool_call> more code"
        assert _clean_llm_response(text) == "Code  more code"

    def test_preserves_normal_content(self):
        from nodes.execute import _clean_llm_response
        text = """utils/main.py
<<<<<<< SEARCH
old
=======
new
>>>>>>> REPLACE"""
        assert _clean_llm_response(text) == text

    def test_complex_minimax_output(self):
        from nodes.execute import _clean_llm_response
        text = """<think>Let me think about this...</think>

utils/helper.js
<<<<<<< SEARCH
var x = 1;
=======
const x = 1;
>>>>>>> REPLACE

</think>more leaked tokens"""
        cleaned = _clean_llm_response(text)
        assert "<think>" not in cleaned
        assert "</think>" not in cleaned
        assert "utils/helper.js" in cleaned
        assert "const x = 1;" in cleaned


class TestExecuteRetryHeuristics:
    def test_retry_when_placeholder_filepath_used(self):
        from nodes.execute import _needs_filepath_retry

        raw = """<filepath>
<<<<<<< SEARCH
old
=======
new
>>>>>>> REPLACE
"""
        assert _needs_filepath_retry(raw, []) is True

    def test_no_retry_when_valid_modification_exists(self):
        from nodes.execute import _needs_filepath_retry

        raw = """src/main.py
<<<<<<< SEARCH
old
=======
new
>>>>>>> REPLACE
"""
        mods = [{"filepath": "src/main.py"}]
        assert _needs_filepath_retry(raw, mods) is False

    def test_no_retry_without_search_replace_blocks(self):
        from nodes.execute import _needs_filepath_retry

        raw = "NO_CHANGES"
        assert _needs_filepath_retry(raw, []) is False
