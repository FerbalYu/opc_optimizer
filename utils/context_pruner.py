"""Context Pruner — condenses multi-round history into compact lessons (v2.7.0).

When running many optimization rounds, the raw round_history grows linearly
and eats into the LLM's context window.  This module provides:

- `condense_history()`: takes the full round_history list and produces a
  compact string of "lessons learned" that fits in ~500 tokens.
- Uses a cheap/fast model (configurable) for the summarization.
- Graceful degradation: if LLM call fails, falls back to mechanical truncation.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("opc.context_pruner")

# ─── Maximum token budget for condensed output ────────────────────
MAX_CONDENSED_CHARS = 1500  # ~375 tokens


def condense_history(
    round_history: List[Dict[str, Any]],
    llm: Any = None,
    current_round: int = 0,
    window_size: int = 2,
) -> str:
    """Condense multi-round history into a compact lessons-learned summary.

    Strategy:
    - Recent N rounds (window_size): keep as-is (detailed)
    - Older rounds: summarize via LLM into 2-3 bullet points
    - If LLM unavailable/fails: use mechanical truncation fallback

    Args:
        round_history: List of round dicts [{round, summary, files_changed, suggestions}]
        llm: Optional LLMService instance for LLM-based condensation
        current_round: Current round number (for determining which are "recent")
        window_size: How many recent rounds to keep in full detail

    Returns:
        A compact string suitable for injection into planning prompts
    """
    if not round_history:
        return ""

    # Split into "recent" (keep detailed) and "older" (condense)
    if len(round_history) <= window_size:
        # Not enough history to condense — return full detail
        return _format_detailed(round_history)

    older = round_history[:-window_size]
    recent = round_history[-window_size:]

    # Try LLM condensation for older rounds
    condensed_older = _condense_via_llm(older, llm)
    if condensed_older is None:
        condensed_older = _condense_mechanical(older)

    # Combine: condensed older + detailed recent
    parts = []
    if condensed_older:
        parts.append("### 历史教训 (浓缩)\n" + condensed_older)
    if recent:
        parts.append("### 近期轮次 (详细)\n" + _format_detailed(recent))

    return "\n\n".join(parts)


def _format_detailed(rounds: List[Dict[str, Any]]) -> str:
    """Format round history entries with full detail."""
    lines = []
    for rh in rounds:
        lines.append(f"**Round {rh.get('round', '?')}**")
        changed = rh.get("files_changed", [])
        if changed:
            lines.append(f"- Files: {', '.join(changed)}")
        summary = rh.get("summary", "")
        if summary:
            lines.append(f"- Changes: {summary[:300]}")
        suggestions = rh.get("suggestions", "")
        if suggestions:
            lines.append(f"- Suggestions: {suggestions[:200]}")
        lines.append("")
    return "\n".join(lines)


def _condense_via_llm(
    rounds: List[Dict[str, Any]],
    llm: Any,
) -> Optional[str]:
    """Use a cheap LLM to condense older rounds into 2-3 bullet points."""
    if llm is None:
        return None

    # Build input text for the LLM
    input_text = _format_detailed(rounds)
    if not input_text.strip():
        return ""

    prompt = f"""You are a concise technical summarizer. Below are logs from past optimization rounds.
Condense them into 2-5 bullet points of KEY LESSONS LEARNED.
Focus on: what was tried, what worked, what to avoid, which files are sensitive.
Each bullet should be ≤ 1 sentence. Use Chinese for the summary.
Total output must be under 300 characters.

Past rounds:
{input_text}

Condensed lessons (bullet points):"""

    try:
        result = llm.generate(
            [
                {"role": "system", "content": "你是一个技术摘要专家。只输出要点，不要多余文字。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        # Truncate if still too long
        if len(result) > MAX_CONDENSED_CHARS:
            result = result[:MAX_CONDENSED_CHARS] + "..."
        logger.info(f"Condensed {len(rounds)} rounds → {len(result)} chars")
        return result.strip()
    except Exception as e:
        logger.warning(f"LLM condensation failed, using fallback: {e}")
        return None


def _condense_mechanical(rounds: List[Dict[str, Any]]) -> str:
    """Fallback: mechanical condensation without LLM.

    Just keeps round number + first 80 chars of summary + files changed.
    """
    lines = []
    for rh in rounds:
        rnum = rh.get("round", "?")
        changed = rh.get("files_changed", [])
        summary = (rh.get("summary", "") or "")[:80]
        files_str = ", ".join(changed[:3])
        if len(changed) > 3:
            files_str += f" (+{len(changed)-3})"
        line = f"- R{rnum}: {summary}"
        if files_str:
            line += f" [{files_str}]"
        lines.append(line)
    return "\n".join(lines)
