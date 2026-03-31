"""Auto Test Generation Plugin for OPC Local Optimizer (v2.2.0).

After code modifications, this plugin generates unit tests for the
changed files using an LLM.  It runs as an optional node inserted
after the ``test`` node (before ``archive``).

Enable by placing the project in a directory with an ``opc_plugins/``
folder, or by adding this plugin's directory to the plugin discovery
path.
"""

import os
import logging
from typing import Dict, Any, List

from plugins import BaseNode

logger = logging.getLogger("opc.plugin.test_gen")


class TestGenNode(BaseNode):
    """Auto-generate unit tests for files modified in the current round."""

    name = "test_gen"
    description = "Auto-generate unit tests for modified files"
    insert_after = "test"  # runs between test and archive

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        modified_files: List[str] = state.get("modified_files", []) or []
        project_path: str = state.get("project_path", "")

        if not modified_files:
            logger.info("No modified files — skipping test generation.")
            state["test_gen_results"] = "No files to generate tests for."
            return state

        # Get LLM instance
        llm = self._get_llm(state)

        generated: List[str] = []
        skipped: List[str] = []

        for rel_path in modified_files:
            abs_path = os.path.join(project_path, rel_path)
            if not os.path.exists(abs_path):
                skipped.append(rel_path)
                continue

            # Only generate tests for source code files
            if not any(rel_path.endswith(ext) for ext in (".py", ".js", ".ts", ".java", ".go")):
                skipped.append(rel_path)
                continue

            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    source_code = f.read()
            except OSError:
                skipped.append(rel_path)
                continue

            # Truncate very large files
            if len(source_code) > 6000:
                source_code = source_code[:6000] + "\n... (truncated)"

            prompt = f"""You are a test generation agent.  Generate comprehensive unit tests
for the following source file.

File: {rel_path}
```
{source_code}
```

Requirements:
- Use the project's native testing framework (pytest for Python, jest/mocha for JS/TS, JUnit for Java, go test for Go)
- Cover edge cases and error paths
- Use descriptive test names
- Keep tests focused and independent

Return ONLY the test code, nothing else.
"""

            try:
                test_code = llm.generate([
                    {"role": "system", "content": "You are a Test Generation Agent. Write high-quality unit tests. Return only code, no explanations."},
                    {"role": "user", "content": prompt},
                ])
            except Exception as e:
                logger.error(f"LLM call failed for {rel_path}: {e}")
                skipped.append(rel_path)
                continue

            # Review generated code for safety
            try:
                from utils.code_reviewer import CodeReviewer
                reviewer = CodeReviewer()
                is_safe, issues = reviewer.review(test_code)
                if not is_safe:
                    logger.warning(f"Test code for {rel_path} rejected by reviewer: {issues}")
                    skipped.append(rel_path)
                    continue
            except ImportError:
                pass  # reviewer not available — proceed anyway

            # Determine output path
            basename = os.path.splitext(os.path.basename(rel_path))[0]
            test_filename = f"test_auto_{basename}{os.path.splitext(rel_path)[1]}"
            test_dir = os.path.join(project_path, "tests")
            os.makedirs(test_dir, exist_ok=True)
            test_path = os.path.join(test_dir, test_filename)

            try:
                with open(test_path, "w", encoding="utf-8") as f:
                    f.write(test_code)
                generated.append(test_filename)
                logger.info(f"✅ Generated test: {test_filename}")
            except OSError as e:
                logger.error(f"Failed to write {test_filename}: {e}")
                skipped.append(rel_path)

        summary_parts = []
        if generated:
            summary_parts.append(f"Generated {len(generated)} test file(s): {', '.join(generated)}")
        if skipped:
            summary_parts.append(f"Skipped {len(skipped)} file(s): {', '.join(skipped)}")

        state["test_gen_results"] = "\n".join(summary_parts) or "Nothing to do."
        logger.info(state["test_gen_results"])
        return state

    # ── helpers ───────────────────────────────────────────────────

    @staticmethod
    def _get_llm(state: Dict[str, Any]):
        """Resolve LLM from state config."""
        from utils.llm import LLMService

        cfg = state.get("llm_config", {}) or {}
        model = cfg.get("test_model") or cfg.get("model") or None
        timeout = cfg.get("timeout", 120)
        if model:
            return LLMService(model_name=model, timeout=timeout)
        return LLMService(timeout=timeout)
