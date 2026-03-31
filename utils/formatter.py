"""Auto-detect and run project code formatters (v2.8.0).

Detects formatters based on project config files:
- pyproject.toml → black / ruff format
- .prettierrc / package.json → prettier --write
- go.mod → gofmt -w
- rustfmt.toml → rustfmt

Usage:
    from utils.formatter import detect_formatter, format_file

    fmt = detect_formatter("/path/to/project")
    if fmt:
        format_file(fmt, "/path/to/project/src/file.py")
"""

import os
import json
import logging
import subprocess
import shutil
from typing import Optional, Tuple

logger = logging.getLogger("opc.formatter")


def detect_formatter(project_path: str) -> Optional[dict]:
    """Auto-detect the project's code formatter.

    Returns:
        Dict with keys: {"name": str, "command": list[str], "extensions": list[str]}
        or None if no formatter detected.
    """
    # Check pyproject.toml for Python formatters
    pyproject = os.path.join(project_path, "pyproject.toml")
    if os.path.exists(pyproject):
        try:
            content = _read_text(pyproject)
            if "[tool.ruff" in content:
                if shutil.which("ruff"):
                    logger.info("Detected formatter: ruff format")
                    return {
                        "name": "ruff format",
                        "command": ["ruff", "format"],
                        "extensions": [".py"],
                    }
            if "[tool.black" in content:
                if shutil.which("black"):
                    logger.info("Detected formatter: black")
                    return {
                        "name": "black",
                        "command": ["black", "--quiet"],
                        "extensions": [".py"],
                    }
        except Exception:
            pass

    # Check for standalone black/ruff in Python projects
    if os.path.exists(os.path.join(project_path, "setup.py")) or \
       os.path.exists(os.path.join(project_path, "setup.cfg")) or \
       os.path.exists(pyproject):
        if shutil.which("ruff"):
            logger.info("Detected formatter: ruff format (default Python)")
            return {
                "name": "ruff format",
                "command": ["ruff", "format"],
                "extensions": [".py"],
            }
        if shutil.which("black"):
            logger.info("Detected formatter: black (default Python)")
            return {
                "name": "black",
                "command": ["black", "--quiet"],
                "extensions": [".py"],
            }

    # Check for prettier (JS/TS/CSS/HTML projects)
    prettierrc_files = [".prettierrc", ".prettierrc.json", ".prettierrc.js", ".prettierrc.yml"]
    has_prettier_config = any(
        os.path.exists(os.path.join(project_path, f)) for f in prettierrc_files
    )
    pkg_json = os.path.join(project_path, "package.json")
    has_prettier_dep = False
    if os.path.exists(pkg_json):
        try:
            pkg = json.loads(_read_text(pkg_json))
            all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            has_prettier_dep = "prettier" in all_deps
        except Exception:
            pass

    if has_prettier_config or has_prettier_dep:
        # Check for local npx prettier first, then global
        if shutil.which("npx"):
            logger.info("Detected formatter: prettier (via npx)")
            return {
                "name": "prettier",
                "command": ["npx", "prettier", "--write"],
                "extensions": [".js", ".jsx", ".ts", ".tsx", ".css", ".html", ".json", ".md"],
            }
        if shutil.which("prettier"):
            logger.info("Detected formatter: prettier")
            return {
                "name": "prettier",
                "command": ["prettier", "--write"],
                "extensions": [".js", ".jsx", ".ts", ".tsx", ".css", ".html", ".json", ".md"],
            }

    # Check for Go formatter
    if os.path.exists(os.path.join(project_path, "go.mod")):
        if shutil.which("gofmt"):
            logger.info("Detected formatter: gofmt")
            return {
                "name": "gofmt",
                "command": ["gofmt", "-w"],
                "extensions": [".go"],
            }

    # Check for Rust formatter
    if os.path.exists(os.path.join(project_path, "Cargo.toml")):
        if shutil.which("rustfmt"):
            logger.info("Detected formatter: rustfmt")
            return {
                "name": "rustfmt",
                "command": ["rustfmt"],
                "extensions": [".rs"],
            }

    logger.debug("No formatter detected for project")
    return None


def parse_formatter_spec(spec: str) -> Optional[dict]:
    """Parse a user-specified formatter string like 'black --quiet' into a config dict.

    Args:
        spec: e.g. "black", "ruff format", "prettier --write"

    Returns:
        Formatter dict or None if empty.
    """
    spec = spec.strip()
    if not spec:
        return None

    parts = spec.split()
    name = parts[0]

    # Infer extensions from the tool name
    ext_map = {
        "black": [".py"],
        "ruff": [".py"],
        "prettier": [".js", ".jsx", ".ts", ".tsx", ".css", ".html", ".json", ".md"],
        "gofmt": [".go"],
        "rustfmt": [".rs"],
    }
    extensions = ext_map.get(name, [])

    return {
        "name": spec,
        "command": parts,
        "extensions": extensions,
    }


def format_file(formatter: dict, filepath: str, project_path: str = "") -> Tuple[bool, str]:
    """Run the formatter on a single file.

    Args:
        formatter: Dict from detect_formatter or parse_formatter_spec
        filepath: Absolute path to the file to format
        project_path: Project root (used as cwd for the formatter)

    Returns:
        (success: bool, message: str)
    """
    if not formatter:
        return False, "No formatter configured"

    # Check file extension
    ext = os.path.splitext(filepath)[1].lower()
    supported_ext = formatter.get("extensions", [])
    if supported_ext and ext not in supported_ext:
        return True, f"Skipped (extension {ext} not in {formatter['name']} scope)"

    cmd = formatter["command"] + [filepath]
    cwd = project_path or os.path.dirname(filepath)

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.debug(f"Formatted {filepath} with {formatter['name']}")
            return True, f"Formatted with {formatter['name']}"
        else:
            stderr = result.stderr.strip()[:200]
            logger.warning(f"Formatter failed on {filepath}: {stderr}")
            return False, f"Formatter error: {stderr}"
    except FileNotFoundError:
        logger.warning(f"Formatter {formatter['name']} not found in PATH")
        return False, f"Formatter {formatter['name']} not installed"
    except subprocess.TimeoutExpired:
        logger.warning(f"Formatter timed out on {filepath}")
        return False, "Formatter timed out"
    except Exception as e:
        logger.warning(f"Formatter error: {e}")
        return False, str(e)


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()
