"""SKILL Optimization Strategy Loader (v2.12.0 — Step 16).

Loads language/framework-specific optimization knowledge from markdown files
and injects them into plan_node prompts for more precise optimization plans.

Skill files use YAML frontmatter for metadata:
    ---
    keywords: [python]
    always: false
    ---
    # content ...

Loading priority:
    1. Project-level `.opcskills/` (highest — project-specific rules)
    2. Global `opcskills/` matched by profile keywords
    3. `always: true` files are always loaded regardless of keywords
"""

import os
import re
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("opc.skill_loader")

__all__ = ["load_skills", "parse_frontmatter", "get_global_skills_dir"]

# ─── Constants ──────────────────────────────────────────────────

# Maximum total characters for combined skill content (~2000 tokens)
MAX_SKILL_CHARS = 8000

# Regex for simple YAML frontmatter: --- ... ---
_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


# ─── Frontmatter Parsing ───────────────────────────────────────

def parse_frontmatter(content: str) -> Dict[str, Any]:
    """Parse YAML frontmatter from markdown content.

    Supports a minimal subset of YAML:
      - `keywords: [a, b, c]` or `keywords: [a]`
      - `always: true` / `always: false`

    Returns:
        Dict with 'keywords' (list[str]) and 'always' (bool).
    """
    result = {"keywords": [], "always": False}

    match = _FRONTMATTER_RE.match(content)
    if not match:
        return result

    frontmatter = match.group(1)

    # Parse keywords: [...]
    kw_match = re.search(r"keywords:\s*\[([^\]]*)\]", frontmatter)
    if kw_match:
        raw = kw_match.group(1).strip()
        if raw:
            result["keywords"] = [k.strip().strip("'\"") for k in raw.split(",") if k.strip()]

    # Parse always: true/false
    always_match = re.search(r"always:\s*(true|false)", frontmatter, re.IGNORECASE)
    if always_match:
        result["always"] = always_match.group(1).lower() == "true"

    return result


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from content, return body only."""
    match = _FRONTMATTER_RE.match(content)
    if match:
        return content[match.end():]
    return content


# ─── File Reading ───────────────────────────────────────────────

def _read_skill_file(path: str) -> Optional[str]:
    """Read a skill file and return its content (without frontmatter)."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return _strip_frontmatter(content).strip()
    except OSError as e:
        logger.warning(f"Failed to read skill file {path}: {e}")
        return None


def _read_skill_meta(path: str) -> Dict[str, Any]:
    """Read a skill file and return its frontmatter metadata."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(2048)  # Frontmatter is always near the top
        return parse_frontmatter(content)
    except OSError as e:
        logger.warning(f"Failed to read skill metadata {path}: {e}")
        return {"keywords": [], "always": False}


# ─── Directory Discovery ───────────────────────────────────────

def get_global_skills_dir() -> str:
    """Get the path to the global opcskills/ directory.

    Located alongside this module:  local_optimizer/opcskills/
    """
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "opcskills",
    )


def _list_skill_files(directory: str) -> List[str]:
    """List all .md files in a directory, sorted alphabetically."""
    if not os.path.isdir(directory):
        return []
    try:
        return sorted(
            os.path.join(directory, f)
            for f in os.listdir(directory)
            if f.endswith(".md") and os.path.isfile(os.path.join(directory, f))
        )
    except OSError:
        return []


# ─── Matching Logic ─────────────────────────────────────────────

def _should_load(meta: Dict[str, Any], languages: List[str], ptype: str) -> bool:
    """Check if a skill file should be loaded based on profile.

    A file is loaded if:
      - `always: true` in its frontmatter, OR
      - any keyword in its frontmatter matches a language or project type.
    """
    if meta.get("always"):
        return True

    keywords = meta.get("keywords", [])
    if not keywords:
        return False

    # Normalize for matching
    langs_lower = {lang.lower() for lang in languages}
    ptype_lower = ptype.lower() if ptype else ""

    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in langs_lower or kw_lower == ptype_lower:
            return True

    return False


# ─── Public API ─────────────────────────────────────────────────

def load_skills(
    project_path: str,
    profile: Optional[Dict[str, Any]] = None,
    max_chars: int = MAX_SKILL_CHARS,
) -> str:
    """Load and return concatenated SKILL content for plan_node.

    Loading priority:
      1. Project-level `.opcskills/` (highest priority, all files loaded)
      2. Global `opcskills/` — keyword-matched + always-loaded files

    Args:
        project_path: Absolute path to the project being optimized.
        profile: Project profile dict (from project_profile.py).
                 Must have 'languages' (list[str]) and 'type' (str).
        max_chars: Maximum total characters for combined output.

    Returns:
        Combined skill content as a string, or empty string if no skills found.
    """
    if profile is None:
        profile = {}

    languages = profile.get("languages", [])
    ptype = profile.get("type", "")

    skills: List[str] = []
    loaded_names: List[str] = []

    # 1. Project-level .opcskills/ (highest priority — all files loaded)
    project_skills_dir = os.path.join(project_path, ".opcskills")
    for fpath in _list_skill_files(project_skills_dir):
        body = _read_skill_file(fpath)
        if body:
            name = os.path.basename(fpath)
            skills.append(body)
            loaded_names.append(f"[project] {name}")

    # 2. Global opcskills/ — keyword match + always
    global_dir = get_global_skills_dir()
    for fpath in _list_skill_files(global_dir):
        meta = _read_skill_meta(fpath)
        if _should_load(meta, languages, ptype):
            body = _read_skill_file(fpath)
            if body:
                name = os.path.basename(fpath)
                skills.append(body)
                loaded_names.append(f"[global] {name}")

    if not skills:
        logger.info("No SKILL files matched")
        return ""

    logger.info(f"Loaded {len(skills)} SKILL files: {', '.join(loaded_names)}")

    # Combine with separator
    combined = "\n\n---\n\n".join(skills)

    # Truncate if over budget
    if len(combined) > max_chars:
        combined = combined[:max_chars].rsplit("\n", 1)[0]
        combined += "\n\n... (SKILL content truncated due to token budget)"
        logger.info(f"SKILL content truncated to {max_chars} chars")

    # Wrap in a section header for the prompt
    return f"\n## Optimization SKILLs (domain-specific best practices):\n\n{combined}"
