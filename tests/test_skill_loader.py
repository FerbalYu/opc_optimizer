"""Tests for SKILL optimization strategy loader (Step 16 — v2.12.0)."""

import os
import pytest
from utils.skill_loader import (
    load_skills,
    parse_frontmatter,
    get_global_skills_dir,
    _should_load,
    _strip_frontmatter,
    _list_skill_files,
    _read_skill_file,
    _read_skill_meta,
)


# ─── Frontmatter Parsing ───────────────────────────────────────


class TestParseFrontmatter:
    """Tests for YAML frontmatter parsing."""

    def test_basic_keywords(self):
        content = "---\nkeywords: [python]\nalways: false\n---\n# Body"
        meta = parse_frontmatter(content)
        assert meta["keywords"] == ["python"]
        assert meta["always"] is False

    def test_multiple_keywords(self):
        content = "---\nkeywords: [javascript, typescript]\nalways: false\n---\n# Body"
        meta = parse_frontmatter(content)
        assert meta["keywords"] == ["javascript", "typescript"]
        assert meta["always"] is False

    def test_always_true(self):
        content = "---\nkeywords: []\nalways: true\n---\n# Body"
        meta = parse_frontmatter(content)
        assert meta["keywords"] == []
        assert meta["always"] is True

    def test_no_frontmatter(self):
        content = "# Just a markdown file\nNo frontmatter here."
        meta = parse_frontmatter(content)
        assert meta["keywords"] == []
        assert meta["always"] is False

    def test_empty_content(self):
        meta = parse_frontmatter("")
        assert meta["keywords"] == []
        assert meta["always"] is False

    def test_quoted_keywords(self):
        content = '---\nkeywords: ["react", "jsx"]\nalways: false\n---\n# Body'
        meta = parse_frontmatter(content)
        assert meta["keywords"] == ["react", "jsx"]

    def test_single_quoted_keywords(self):
        content = "---\nkeywords: ['vue']\nalways: false\n---\n# Body"
        meta = parse_frontmatter(content)
        assert meta["keywords"] == ["vue"]

    def test_always_case_insensitive(self):
        content = "---\nkeywords: []\nalways: True\n---\n# Body"
        meta = parse_frontmatter(content)
        assert meta["always"] is True

    def test_empty_keywords_list(self):
        content = "---\nkeywords: []\nalways: false\n---\n# Body"
        meta = parse_frontmatter(content)
        assert meta["keywords"] == []


class TestStripFrontmatter:
    """Tests for frontmatter stripping."""

    def test_strip_basic(self):
        content = "---\nkeywords: [python]\n---\n# Body content"
        body = _strip_frontmatter(content)
        assert body == "# Body content"

    def test_strip_no_frontmatter(self):
        content = "# Just body"
        body = _strip_frontmatter(content)
        assert body == "# Just body"


# ─── Matching Logic ─────────────────────────────────────────────


class TestShouldLoad:
    """Tests for SKILL matching logic."""

    def test_always_true_matches(self):
        meta = {"always": True, "keywords": []}
        assert _should_load(meta, [], "") is True

    def test_keyword_matches_language(self):
        meta = {"always": False, "keywords": ["python"]}
        assert _should_load(meta, ["python"], "python") is True

    def test_keyword_matches_type(self):
        meta = {"always": False, "keywords": ["vue"]}
        assert _should_load(meta, ["javascript", "vue"], "vue") is True

    def test_keyword_no_match(self):
        meta = {"always": False, "keywords": ["rust"]}
        assert _should_load(meta, ["python"], "python") is False

    def test_empty_keywords_no_match(self):
        meta = {"always": False, "keywords": []}
        assert _should_load(meta, ["python"], "python") is False

    def test_case_insensitive_match(self):
        meta = {"always": False, "keywords": ["Python"]}
        assert _should_load(meta, ["python"], "python") is True

    def test_multiple_keywords_partial_match(self):
        meta = {"always": False, "keywords": ["javascript", "typescript"]}
        assert _should_load(meta, ["javascript"], "javascript") is True

    def test_no_languages_no_type(self):
        meta = {"always": False, "keywords": ["python"]}
        assert _should_load(meta, [], "") is False


# ─── File Operations ───────────────────────────────────────────


class TestFileOps:
    """Tests for file listing and reading."""

    def test_list_skill_files(self, tmp_path):
        (tmp_path / "a.md").write_text("# A", encoding="utf-8")
        (tmp_path / "b.md").write_text("# B", encoding="utf-8")
        (tmp_path / "c.txt").write_text("# Not MD", encoding="utf-8")
        files = _list_skill_files(str(tmp_path))
        assert len(files) == 2
        assert all(f.endswith(".md") for f in files)

    def test_list_skill_files_empty_dir(self, tmp_path):
        files = _list_skill_files(str(tmp_path))
        assert files == []

    def test_list_skill_files_nonexistent(self):
        files = _list_skill_files("/nonexistent/path")
        assert files == []

    def test_read_skill_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("---\nkeywords: [python]\n---\n# Python Tips\n- Use slots", encoding="utf-8")
        content = _read_skill_file(str(f))
        assert "# Python Tips" in content
        assert "keywords" not in content  # Frontmatter stripped

    def test_read_skill_meta(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("---\nkeywords: [go]\nalways: false\n---\n# Body", encoding="utf-8")
        meta = _read_skill_meta(str(f))
        assert meta["keywords"] == ["go"]
        assert meta["always"] is False


# ─── Global Skills Dir ──────────────────────────────────────────


class TestGlobalSkillsDir:
    """Tests for global skill directory resolution."""

    def test_global_dir_exists(self):
        """Verify our opcskills/ directory exists and has files."""
        d = get_global_skills_dir()
        assert os.path.isdir(d), f"opcskills/ directory not found at {d}"
        md_files = [f for f in os.listdir(d) if f.endswith(".md")]
        assert len(md_files) >= 7, f"Expected >=7 skill files, found {len(md_files)}"

    def test_all_skills_have_frontmatter(self):
        """Every skill file should have valid frontmatter."""
        d = get_global_skills_dir()
        for fname in os.listdir(d):
            if not fname.endswith(".md"):
                continue
            with open(os.path.join(d, fname), "r", encoding="utf-8") as f:
                content = f.read()
            meta = parse_frontmatter(content)
            # Every file should have 'always' defined (True or False)
            assert isinstance(meta["always"], bool), f"{fname} missing 'always' field"
            assert isinstance(meta["keywords"], list), f"{fname} missing 'keywords' field"


# ─── Load Skills (Integration) ─────────────────────────────────


class TestLoadSkills:
    """Integration tests for the load_skills function."""

    def test_python_profile(self, tmp_path):
        """Python profile should load python-performance + always skills."""
        profile = {"type": "python", "languages": ["python"]}
        result = load_skills(str(tmp_path), profile)
        assert "Optimization SKILLs" in result
        # Should contain python-specific content
        assert "__slots__" in result or "slots" in result.lower()
        # Should contain security (always)
        assert "SQL" in result or "Security" in result
        # Should contain clean code (always)
        assert "DRY" in result or "Clean Code" in result

    def test_vue_profile(self, tmp_path):
        """Vue profile should load vue-optimization + always skills."""
        profile = {"type": "vue", "languages": ["javascript", "typescript", "vue"]}
        result = load_skills(str(tmp_path), profile)
        assert "computed" in result or "v-show" in result
        # Also loads JS skill (language match)
        assert "tree-shaking" in result or "bundle" in result.lower()

    def test_react_profile(self, tmp_path):
        """React profile should load react-patterns + always skills."""
        profile = {"type": "react", "languages": ["javascript", "typescript", "jsx", "tsx"]}
        result = load_skills(str(tmp_path), profile)
        assert "React.memo" in result or "useMemo" in result

    def test_go_profile(self, tmp_path):
        """Go profile should load go-performance + always skills."""
        profile = {"type": "go", "languages": ["go"]}
        result = load_skills(str(tmp_path), profile)
        assert "sync.Pool" in result or "goroutine" in result

    def test_unknown_profile_only_always(self, tmp_path):
        """Unknown profile should only load always-on skills."""
        profile = {"type": "unknown", "languages": []}
        result = load_skills(str(tmp_path), profile)
        # Should have security + clean code but NOT language-specific
        assert "Security" in result or "SQL" in result
        assert "Clean Code" in result or "DRY" in result
        # Should NOT have python/js/go specific content
        assert "__slots__" not in result
        assert "tree-shaking" not in result
        assert "sync.Pool" not in result

    def test_empty_profile(self, tmp_path):
        """Empty profile dict should still load always-on skills."""
        result = load_skills(str(tmp_path), {})
        assert result != ""
        assert "Security" in result or "Clean Code" in result

    def test_none_profile(self, tmp_path):
        """None profile should still work (default to empty)."""
        result = load_skills(str(tmp_path), None)
        assert result != ""

    def test_project_skills_override(self, tmp_path):
        """Project-level .opcskills/ files should be loaded first."""
        # Create project-level skill
        skill_dir = tmp_path / ".opcskills"
        skill_dir.mkdir()
        (skill_dir / "our-rules.md").write_text(
            "---\nkeywords: []\nalways: false\n---\n# Our Project Rules\n- Always use UPPERCASE_CONSTANTS",
            encoding="utf-8",
        )
        profile = {"type": "python", "languages": ["python"]}
        result = load_skills(str(tmp_path), profile)
        assert "UPPERCASE_CONSTANTS" in result

    def test_project_skills_empty_dir(self, tmp_path):
        """Empty .opcskills/ should not cause errors."""
        (tmp_path / ".opcskills").mkdir()
        profile = {"type": "python", "languages": ["python"]}
        result = load_skills(str(tmp_path), profile)
        # Should still load global skills normally
        assert result != ""

    def test_truncation(self, tmp_path):
        """Skills exceeding max_chars should be truncated."""
        profile = {"type": "python", "languages": ["python"]}
        result = load_skills(str(tmp_path), profile, max_chars=100)
        # Result with section header will exceed 100, but content should be truncated
        assert "truncated" in result.lower()

    def test_no_global_dir(self, tmp_path, monkeypatch):
        """If global opcskills/ doesn't exist, should still load project skills."""
        # Create project-level skill
        skill_dir = tmp_path / ".opcskills"
        skill_dir.mkdir()
        (skill_dir / "custom.md").write_text("# Custom Rule\n- Do X", encoding="utf-8")

        # Monkeypatch global dir to nonexistent
        monkeypatch.setattr(
            "utils.skill_loader.get_global_skills_dir",
            lambda: str(tmp_path / "nonexistent_opcskills"),
        )
        result = load_skills(str(tmp_path), {"type": "python", "languages": ["python"]})
        assert "Custom Rule" in result
