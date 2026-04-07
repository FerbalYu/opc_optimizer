"""Tests for scripts/gen_skill_docs.py."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.gen_skill_docs import generate_skill_docs


def test_generate_skill_docs_creates_core_docs(tmp_path):
    generated = generate_skill_docs(output_dir=str(tmp_path))
    names = sorted(os.path.basename(path) for path in generated)

    assert names == ["execute.md", "plan.md", "report.md", "test.md"]

    plan_doc = (tmp_path / "plan.md").read_text(encoding="utf-8")
    assert "# Skill: plan" in plan_doc
    assert "Entrypoint: `nodes.plan:plan_node`" in plan_doc
    assert "## Inputs" in plan_doc
    assert "- project_path" in plan_doc
    assert "## Outputs" in plan_doc
    assert "- current_plan" in plan_doc

