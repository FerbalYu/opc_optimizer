"""Tests for scripts/check_skill_docs_freshness.py."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.check_skill_docs_freshness import check_skill_docs_freshness
from scripts.gen_skill_docs import generate_skill_docs


def test_freshness_check_passes_for_newly_generated_docs(tmp_path):
    generate_skill_docs(output_dir=str(tmp_path))
    ok, problems = check_skill_docs_freshness(str(tmp_path))
    assert ok is True
    assert problems == []


def test_freshness_check_detects_outdated_doc(tmp_path):
    generate_skill_docs(output_dir=str(tmp_path))
    plan_doc = tmp_path / "plan.md"
    plan_doc.write_text(plan_doc.read_text(encoding="utf-8") + "\n# stale", encoding="utf-8")

    ok, problems = check_skill_docs_freshness(str(tmp_path))
    assert ok is False
    assert any("Outdated generated doc: plan.md" in p for p in problems)

