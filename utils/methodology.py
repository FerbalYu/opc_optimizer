"""Optimization methodology — principles injected into every LLM prompt (v2.2.0).

This module encodes the working discipline of the optimizer so that any
LLM (strong or weak) follows a structured, careful approach when
modifying code.
"""

# ── System-level methodology injected into every planning prompt ─────

PLAN_METHODOLOGY = """
## Methodology — You MUST follow these rules

### Principles
1. **Read before write** — You must reference ACTUAL code from the files above. Never propose changes to code you haven't seen.
2. **Minimal invasion** — Only change what is strictly necessary for the optimization goal. Do NOT refactor unrelated code.
3. **Bottom-up order** — Propose changes in dependency order: utilities/helpers first → business logic → entry points → UI last.
4. **One thing at a time** — Each change item should do ONE thing. Do not mix "add type hints" with "refactor loop" in a single modification.
5. **Preserve behavior** — Changes must not break existing functionality. If unsure, note the risk explicitly.

### Plan Format
- Group changes by file, not by theme
- For each change: state the EXACT function/class/line being changed
- Explain WHY, not just WHAT
- Estimate risk: LOW / MEDIUM / HIGH
- If a change fails, the remaining changes should still be valid (independent changes)
"""

# ── System-level methodology injected into every execution prompt ────

EXECUTE_METHODOLOGY = """
## Methodology — You MUST follow these rules

### Code Modification Rules
1. **Exact match** — The `old_content_snippet` MUST be an exact, character-for-character substring of the current file. Copy it precisely.
2. **Minimal diff** — Replace only the smallest snippet needed. Do NOT rewrite entire functions when changing one line.
3. **No side effects** — Your change must not alter the behavior of code outside the modified function/block.
4. **Consistent style** — Match the existing code style (indentation, naming, quotes) of the file you are modifying.
5. **Dependency aware** — If adding an import, place it at the top of the file with existing imports. If renaming a function, check all call sites.

### Safety Checks
- Do NOT add `eval()`, `exec()`, `os.system()`, `subprocess.call()` with `shell=True`
- Do NOT remove error handling (try/except) without replacing it
- Do NOT delete backup/logging/safety code
- Do NOT introduce circular imports

### Quality Bar
- Every modified function should have a clear docstring
- Variable names should be descriptive (no single-letter names except in list comprehensions)
- Magic numbers should be named constants
"""

# ── System-level methodology injected into review/test prompt ────────

REVIEW_METHODOLOGY = """
## Review Methodology — You MUST follow these rules

### Review Checklist
1. **Correctness** — Does the change do what the plan says? Are edge cases handled?
2. **Safety** — No dangerous patterns (eval, shell injection, path traversal)?
3. **Regressions** — Could this change break existing behavior? Check all callers.
4. **Style** — Consistent with the rest of the codebase?
5. **Completeness** — Are all necessary changes included? Missing import? Missing update to callers?

### Scoring
- Rate each change: PASS / WARN / FAIL
- FAIL = must be reverted or fixed before next round
- WARN = acceptable but should be improved in future rounds
- PASS = good quality, no issues
"""
