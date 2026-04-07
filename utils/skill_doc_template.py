"""Utilities for loading and rendering skill markdown templates."""

import os
from typing import Dict


def get_skill_templates_dir() -> str:
    """Return absolute path of the `skills/` template directory."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "skills",
    )


def load_template(template_name: str) -> str:
    """Load one markdown template by filename."""
    if not template_name.endswith(".md.tmpl"):
        raise ValueError("Template name must end with .md.tmpl")

    path = os.path.join(get_skill_templates_dir(), template_name)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Template not found: {path}")

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def render_template(template_name: str, context: Dict[str, str]) -> str:
    """Render template using Python named placeholders."""
    template = load_template(template_name)
    try:
        return template.format(**context)
    except KeyError as exc:
        missing = str(exc).strip("'")
        raise ValueError(
            f"Missing template context key: {missing} for template {template_name}"
        ) from exc

