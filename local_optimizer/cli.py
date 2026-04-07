"""Compatibility shim for ``from local_optimizer.cli import ...`` imports."""

# Re-export both public and test-used private symbols explicitly.
from cli import (
    _check_dangerous_patterns_in_values,
    _check_dependencies,
    _get_toml_parser,
    find_project_root,
    validate_pyproject_toml,
)

__all__ = [
    "validate_pyproject_toml",
    "find_project_root",
    "_check_dependencies",
    "_get_toml_parser",
    "_check_dangerous_patterns_in_values",
]
