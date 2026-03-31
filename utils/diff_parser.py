"""Diff parser — SEARCH/REPLACE block parser + fuzzy matching (v2.4.0).

Supports the Aider-style SEARCH/REPLACE format:
    filepath
    <<<<<<< SEARCH
    exact old code
    =======
    new replacement code
    >>>>>>> REPLACE

Also supports fallback JSON format for backward compatibility.
"""

import re
import difflib
import logging
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger("opc.diff_parser")

# ─── SEARCH/REPLACE Block Parser ─────────────────────────────────────

# Regex pattern for SEARCH/REPLACE blocks
_SR_PATTERN = re.compile(
    r'(?:^|\n)([^\n]+)\n'           # filepath line
    r'<<<<<<< SEARCH\n'             # start marker
    r'(.*?)\n'                       # search content (non-greedy)
    r'=======\n'                     # separator
    r'(.*?)\n'                       # replace content (non-greedy)
    r'>>>>>>> REPLACE',              # end marker
    re.DOTALL
)


def _sanitize_filepath(raw: str) -> Optional[str]:
    """Clean & validate extracted filepath. Returns None if invalid.
    
    Filters out common LLM artifacts:
    - HTML/XML tags (<filepath>, </think>, <minimax:tool_call>)
    - Markdown formatting (**bold**)
    - Placeholder tokens
    - Overly long or empty strings
    """
    # Strip whitespace, backticks, and markdown bold markers
    path = raw.strip().strip('`').strip('*').strip()
    
    if not path:
        return None
    
    # Reject HTML/XML tags (e.g. <filepath>, </think>, <minimax:tool_call>)
    if re.match(r'^<.*>$', path) or path.startswith('</'):
        logger.debug(f"Rejected tag-like filepath: {raw!r}")
        return None
    
    # Reject if contains < or > (likely tag fragments)
    if '<' in path or '>' in path:
        logger.debug(f"Rejected filepath containing angle brackets: {raw!r}")
        return None
    
    # Must contain at least one path separator or file extension dot
    if not re.search(r'[/\\.]', path):
        logger.debug(f"Rejected filepath without path separators or extension: {raw!r}")
        return None
    
    # Reject common placeholder names
    placeholders = {'filepath', 'file', 'filename', 'path', 'file_path'}
    if path.lower().strip('<>') in placeholders:
        return None
    
    # Reject overly long paths
    if len(path) > 200:
        return None
    
    # Reject markdown headings
    if path.startswith('#'):
        return None
    
    return path


def parse_search_replace(text: str) -> List[Dict[str, str]]:
    """Parse SEARCH/REPLACE blocks from LLM output.
    
    Args:
        text: Raw LLM output containing one or more SEARCH/REPLACE blocks.
        
    Returns:
        List of modification dicts with keys:
        filepath, old_content_snippet, new_content, reason
    """
    modifications = []
    
    # Find all SEARCH/REPLACE blocks
    matches = _SR_PATTERN.findall(text)
    for raw_filepath, search, replace in matches:
        filepath = _sanitize_filepath(raw_filepath)
        if filepath is None:
            logger.warning(f"Skipped invalid filepath from LLM output: {raw_filepath!r}")
            continue
        modifications.append({
            "filepath": filepath,
            "old_content_snippet": search,
            "new_content": replace,
            "reason": "SEARCH/REPLACE block",
        })
    
    if modifications:
        logger.info(f"Parsed {len(modifications)} SEARCH/REPLACE blocks")
    else:
        if matches:
            logger.warning(f"Found {len(matches)} SEARCH/REPLACE blocks but all had invalid filepaths")
    
    return modifications


def parse_json_fallback(text: str) -> List[Dict[str, str]]:
    """Parse JSON format modifications (backward compatibility).
    
    Tries to extract a JSON object with a 'modifications' key from the text.
    """
    import json
    
    # Try to find JSON in the text
    # Look for ```json ... ``` blocks first
    json_match = re.search(r'```json\s*\n(.*?)\n\s*```', text, re.DOTALL)
    if json_match:
        text = json_match.group(1)
    
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data.get("modifications", [])
        return []
    except json.JSONDecodeError:
        # Try to find a JSON object anywhere in the text
        brace_start = text.find('{')
        brace_end = text.rfind('}')
        if brace_start >= 0 and brace_end > brace_start:
            try:
                data = json.loads(text[brace_start:brace_end + 1])
                if isinstance(data, dict):
                    return data.get("modifications", [])
            except json.JSONDecodeError:
                pass
    return []


def parse_llm_output(text: str) -> List[Dict[str, str]]:
    """Parse LLM output, trying SEARCH/REPLACE first, then JSON fallback.
    
    Returns:
        List of modification dicts.
    """
    # Try SEARCH/REPLACE format first
    mods = parse_search_replace(text)
    if mods:
        return mods
    
    # Fallback to JSON format
    logger.info("No SEARCH/REPLACE blocks found, trying JSON fallback...")
    mods = parse_json_fallback(text)
    if mods:
        logger.info(f"Parsed {len(mods)} modifications from JSON")
    return mods


# ─── Fuzzy Matching ──────────────────────────────────────────────────

def fuzzy_find_and_replace(
    file_content: str,
    search_text: str,
    replace_text: str,
    min_similarity: float = 0.6,
    auto_threshold: float = 0.85,
) -> Tuple[Optional[str], float, str]:
    """Find and replace text with fuzzy matching fallback.
    
    Strategy:
    1. Exact match → apply immediately
    2. Single fuzzy match ≥ auto_threshold → apply + warning
    3. Single fuzzy match ≥ min_similarity → needs user confirmation
    4. Multiple indistinguishable candidates (Opt-2) → "ambiguous" (reject)
    5. Below min_similarity → reject
    
    Args:
        file_content: Full file content to search in.
        search_text: Text to search for (may not be exact).
        replace_text: Replacement text.
        min_similarity: Minimum similarity ratio to consider (default 0.6).
        auto_threshold: Auto-apply threshold (default 0.85).
        
    Returns:
        Tuple of (patched_content_or_None, similarity_ratio, status_message)
        Status: "exact", "auto_fuzzy", "needs_confirm", "rejected", "ambiguous"
    """
    # 1. Try exact match
    if search_text in file_content:
        patched = file_content.replace(search_text, replace_text, 1)
        return patched, 1.0, "exact"
    
    # 2. Try fuzzy matching — find ALL matching regions above min_similarity
    search_lines = search_text.splitlines()
    file_lines = file_content.splitlines()
    
    if not search_lines or not file_lines:
        return None, 0.0, "rejected"
    
    search_len = len(search_lines)
    
    # Collect ALL candidates above the minimum threshold
    candidates = []  # list of (ratio, start_idx, end_idx)
    for i in range(max(1, len(file_lines) - search_len + 1)):
        window_end = min(i + search_len + 2, len(file_lines))
        window = file_lines[i:window_end]
        
        matcher = difflib.SequenceMatcher(
            None,
            "\n".join(search_lines),
            "\n".join(window),
        )
        ratio = matcher.ratio()
        
        if ratio >= min_similarity:
            candidates.append((ratio, i, min(i + search_len, len(file_lines))))
    
    if not candidates:
        return None, 0.0, "rejected"
    
    # Sort by ratio descending
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_ratio, best_start, best_end = candidates[0]

    # ── Opt-2: Multi-candidate ambiguity guard ────────────────────────────
    # If 2+ candidates differ by less than 5% in similarity → ambiguous
    if len(candidates) >= 2:
        second_ratio = candidates[1][0]
        if (best_ratio - second_ratio) < 0.05:
            candidate_summaries = [
                f"lines {s+1}-{e} (similarity={r:.2%})"
                for r, s, e in candidates[:5]
            ]
            logger.warning(
                f"Ambiguous fuzzy match: {len(candidates)} indistinguishable candidates — "
                + ", ".join(candidate_summaries)
            )
            return None, best_ratio, "ambiguous"
    
    # Build patched content from the single best candidate
    matched_text = "\n".join(file_lines[best_start:best_end])
    patched = file_content.replace(matched_text, replace_text, 1)
    
    if best_ratio >= auto_threshold:
        logger.warning(
            f"Fuzzy match applied (similarity={best_ratio:.2%}). "
            f"Original: {matched_text[:80]}..."
        )
        return patched, best_ratio, "auto_fuzzy"
    else:
        # Needs user confirmation
        return patched, best_ratio, "needs_confirm"



def generate_diff_preview(
    filepath: str,
    original: str,
    patched: str,
    context_lines: int = 3,
) -> str:
    """Generate a unified diff preview for display.
    
    Args:
        filepath: File path for the diff header.
        original: Original file content.
        patched: Patched file content.
        context_lines: Number of context lines around changes.
        
    Returns:
        Unified diff string.
    """
    original_lines = original.splitlines(keepends=True)
    patched_lines = patched.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        original_lines,
        patched_lines,
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
        n=context_lines,
    )
    return "".join(diff)
