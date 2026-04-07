"""
CLI entry points for OPC Optimizer.

This module provides command-line interface functions for:
- test: Run project tests
- format: Format code using configured formatter
- lint: Run linting tools
- security_check: Run security scanning tools (including pyproject.toml validation)
"""

import sys
import subprocess
import argparse
import logging
import os
import json
import re
import signal
from pathlib import Path
from typing import Optional


def find_project_root() -> Path:
    """Find project root by looking for pyproject.toml.
    
    Searches upward from the current file's directory until finding
    pyproject.toml or reaching the filesystem root.
    
    NOTE: This function assumes pyproject.toml is located at the same level
    as the src/ directory (project root). If the module is imported as part
    of an installed package where pyproject.toml may be in a different location,
    set the OPC_PROJECT_ROOT environment variable to the project root path.
    
    Returns:
        Path to project root directory
        
    Raises:
        RuntimeError: If pyproject.toml is not found and OPC_PROJECT_ROOT is not set
    """
    # Prefer runtime CWD to support tests and CLI execution from arbitrary repos.
    current = Path.cwd().resolve()
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent

    # Fallback to module location scan for legacy invocation patterns.
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    
    # Check environment variable fallback
    env_root = os.environ.get('OPC_PROJECT_ROOT')
    if env_root:
        return Path(env_root)
    
    # No pyproject.toml found - raise explicit error with context information
    current_cwd = os.getcwd() or 'unknown'
    env_value = os.environ.get('OPC_PROJECT_ROOT', 'not set')
    raise RuntimeError(
        f"Could not find pyproject.toml. "
        f"Current directory: {current_cwd}; "
        f"OPC_PROJECT_ROOT: {env_value}. "
        f"Please ensure you are running OPC from a valid project directory, "
        f"or set the OPC_PROJECT_ROOT environment variable to the project root path."
    )


def _get_toml_parser():
    """Get a TOML parser that works on this Python version.
    
    Returns:
        A callable that takes a string and returns a parsed TOML dict.
        Uses tomllib for Python 3.11+, tomli as fallback for older versions.
        
    Raises:
        ImportError: If neither tomllib nor tomli is available
    """
    # Try Python 3.11+ standard library first
    try:
        import tomllib
        return tomllib.loads
    except ImportError:
        pass
    
    # Fall back to tomli for older Python versions
    try:
        import tomli
        return tomli.loads
    except ImportError:
        raise ImportError(
            "TOML parsing requires 'tomllib' (Python 3.11+) or 'tomli' package. "
            "Install tomli: pip install tomli"
        )


def _check_dangerous_patterns_in_values(
    values: list[str], 
    dangerous_patterns: list[tuple], 
    issues: list[str]
) -> None:
    """Check for dangerous patterns in string values.
    
    This function checks all passed string values against dangerous patterns
    to detect potential security issues like code injection or dangerous commands.
    Note: Only actual string values are checked, not comments.
    
    Args:
        values: List of parsed string values to check (e.g., script commands, deps)
        dangerous_patterns: List of (pattern, message) tuples
        issues: List to append issues to (modified in place)
    """
    for value in values:
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        if "del /f /q" in lowered:
            issues.append("SECURITY: Found Windows force delete command (del /f /q) - destructive operation")
        for pattern, message in dangerous_patterns:
            if re.search(pattern, value):
                issues.append(message)


def _check_dependencies(
    dependencies: list[str],
    dangerous_pkgs: list[str],
    issues: list[str],
    group_name: Optional[str] = None
) -> None:
    """Check dependencies for security issues.
    
    This function performs security checks on dependency lists:
    1. Detects dangerous packages that could enable code execution
    2. Flags wildcard versions in production dependencies
    
    Args:
        dependencies: List of dependency strings (e.g., "package>=1.0")
        dangerous_pkgs: List of package names to flag as dangerous
        issues: List to append issues to (modified in place)
        group_name: Optional group name for optional dependencies
    """
    for dep in dependencies:
        # Parse package name and version from dependency string
        # Format: "package[extra]>=1.0,<2.0" or "package"
        match = re.match(r'^([a-zA-Z0-9_-]+)', dep.strip())
        if not match:
            continue
            
        pkg_name = match.group(1)
        group_prefix = f"[{group_name}] " if group_name else ""
        
        # Check for dangerous packages that could enable arbitrary code execution
        # These packages can execute arbitrary code during serialization/deserialization
        # or can inject code into builds/distributions
        for dangerous_pkg in dangerous_pkgs:
            if pkg_name.lower() == dangerous_pkg.lower():
                if dangerous_pkg == 'pick':
                    issues.append(
                        f"SECURITY: {group_prefix}Package '{pkg_name}' is dangerous - "
                        f"can enable arbitrary code execution"
                    )
                elif dangerous_pkg in ('pip', 'setuptools'):
                    issues.append(
                        f"WARNING: {group_prefix}Package '{pkg_name}' is not recommended as a dependency - "
                        f"use pip-installed tools only in CI/build environments"
                    )
                elif dangerous_pkg in ('pyinstaller', 'cx_Freeze', 'pyarmor', 'pyobfuscate', 'Nuitka', 'py2exe'):
                    # Packaging and code obfuscation tools that could inject malicious code
                    issues.append(
                        f"SECURITY: {group_prefix}Package '{pkg_name}' is a packaging/obfuscation tool - "
                        f"potential for code injection in distributions"
                    )
                else:
                    issues.append(
                        f"INFO: {group_prefix}Package '{pkg_name}' in dangerous packages list"
                    )
        
        # Check for wildcard versions (only flag in production deps without group)
        if not group_name:
            version_match = re.search(r'[\s=>!<~]+([0-9.*^~]+)', dep)
            if version_match and '*' in version_match.group(1):
                issues.append(
                    f"WARNING: {group_prefix}Wildcard version in dependency '{dep}' - "
                    f"may cause inconsistent installs"
                )


def _verify_version_file_integrity(project_root: Path) -> tuple[int, list[str]]:
    """Verify the integrity of the version file for dynamic versioning.
    
    This function checks if the version file contains only safe, expected content
    to prevent arbitrary code execution through a compromised version file.
    
    Args:
        project_root: Path to project root directory
        
    Returns:
        Tuple of (exit_code, list of warnings/issues found)
    """
    issues: list[str] = []
    exit_code = 0
    
    version_file = project_root / "src" / "opc_optimizer" / "_version.py"
    
    if not version_file.exists():
        # Version file may be generated at build time by setuptools-scm
        return exit_code, issues
    
    try:
        content = version_file.read_text(encoding="utf-8")
        
        # Check for suspicious patterns that shouldn't be in a version file
        suspicious_patterns = [
            (r'import\s+os\.system', "Version file contains os.system import"),
            (r'import\s+subprocess', "Version file contains subprocess import"),
            (r'eval\s*\(', "Version file contains eval() call"),
            (r'exec\s*\(', "Version file contains exec() call"),
            (r'__import__\s*\(', "Version file contains dynamic import"),
            (r'open\s*\(', "Version file contains file operations"),
            (r'requests\.', "Version file contains HTTP requests"),
            (r'urllib', "Version file contains URL operations"),
            (r'socket\.', "Version file contains socket operations"),
            (r'base64', "Version file contains base64 operations"),
            (r'compile\s*\(', "Version file contains compile() call"),
            (r'marshal\.loads', "Version file contains marshal operations"),
            (r'pickle\.loads', "Version file contains pickle operations"),
            (r'yaml\.load', "Version file contains YAML load (unsafe)"),
        ]
        
        for pattern, message in suspicious_patterns:
            if re.search(pattern, content):
                issues.append(f"SECURITY: {message} - potential code injection")
                exit_code = 1
        
        # Version file should only contain version info, not complex logic
        lines = content.split('\n')
        code_lines = [l for l in lines if l.strip() and not l.strip().startswith('#') 
                      and not l.strip().startswith('from') 
                      and not l.strip().startswith('import')
                      and '=' not in l
                      and not l.strip().startswith('__')]
        
        if len(code_lines) > 5:
            issues.append(f"WARNING: Version file contains {len(code_lines)} non-trivial code lines - "
                         f"expected minimal content. Verify file integrity.")
            exit_code = 1
                        
    except IOError as e:
        issues.append(f"WARNING: Cannot read version file for integrity check: {e}")
    except Exception as e:
        issues.append(f"WARNING: Error during version file integrity check: {e}")
    
    return exit_code, issues


def validate_pyproject_toml(project_root: Path) -> tuple[int, list[str]]:
    """Validate pyproject.toml for security compliance and best practices.
    
    This function checks:
    - Required fields are present
    - Version constraints are secure (no wildcard versions in production)
    - Dependencies don't include potentially dangerous packages
    - Scripts don't reference dangerous commands
    - Version file integrity for dynamic versioning
    
    Note: Dangerous pattern detection is applied only to parsed string values,
    not to TOML comments, to avoid false positives from security warnings
    in documentation comments.
    
    Args:
        project_root: Path to project root directory
        
    Returns:
        Tuple of (exit_code, list of warnings/issues found)
    """
    issues: list[str] = []
    exit_code = 0
    
    pyproject_path = project_root / "pyproject.toml"
    
    if not pyproject_path.exists():
        issues.append("ERROR: pyproject.toml not found in project root")
        return 1, issues
    
    try:
        content = pyproject_path.read_text(encoding="utf-8")
    except IOError as e:
        issues.append(f"ERROR: Cannot read pyproject.toml: {e}")
        return 1, issues

    # Raw-content guard catches dangerous commands even when TOML parsing fails.
    if re.search(r"del\s+/f\s+/q", content, re.IGNORECASE):
        issues.append("SECURITY: Found Windows force delete command (del /f /q) - destructive operation")
        exit_code = 1
    
    # Define dangerous patterns for code injection risks
    # These patterns check for dangerous Python constructs that could enable code injection
    code_injection_patterns = [
        (r'eval\s*\(', "SECURITY: Found 'eval()' call - potential code injection"),
        (r'exec\s*\(', "SECURITY: Found 'exec()' call - potential code injection"),
        (r'__import__\s*\(', "SECURITY: Found dynamic import - potential code injection"),
        (r'subprocess\.run.*shell\s*=\s*True', "SECURITY: shell=True in subprocess - potential command injection"),
        (r'os\.system\s*\(', "SECURITY: Found os.system() - potential command injection"),
        (r'os\.popen\s*\(', "SECURITY: Found os.popen() - potential command injection"),
        (r'rm\s+-rf', "SECURITY: Found 'rm -rf' command - destructive operation"),
        (r'\bdel\s+/f\s+/q\b', "SECURITY: Found Windows force delete command - destructive operation"),
        (r'\$[A-Za-z_][A-Za-z0-9_]*', "SECURITY: Found shell expansion variable - potential shell expansion risk"),
        (r'base64\.b64decode', "SECURITY: Found base64.b64decode - potential code obfuscation"),
    ]
    
    try:
        parse_toml = _get_toml_parser()
        config = parse_toml(content)
    except Exception as e:
        issues.append(f"ERROR: Failed to parse pyproject.toml: {e}")
        return 1, issues
    
    # Check required fields
    if 'project' not in config:
        issues.append("ERROR: Missing required [project] section in pyproject.toml")
        return 1, issues
    
    project = config['project']
    
    # Check for required metadata
    if 'name' not in project:
        issues.append("ERROR: Missing required 'name' field in [project] section")
        exit_code = 1
    
    if 'version' not in project and 'dynamic' not in project:
        issues.append("ERROR: Cannot read project version metadata: missing 'version' or 'dynamic.version'")
        exit_code = 1
    
    # Check dependencies for security issues
    dangerous_pkgs = ['pick', 'pip', 'setuptools', 'pyinstaller', 'cx_Freeze', 
                      'pyarmor', 'pyobfuscate', 'Nuitka', 'py2exe']
    
    # Check main dependencies
    if 'dependencies' in project:
        _check_dependencies(project['dependencies'], dangerous_pkgs, issues)
    
    # Check optional dependencies
    if 'optional-dependencies' in project:
        for group_name, deps in project['optional-dependencies'].items():
            _check_dependencies(deps, dangerous_pkgs, issues, group_name)
    
    # Check scripts for dangerous commands
    if 'scripts' in project:
        for script_name, script_cmd in project['scripts'].items():
            if isinstance(script_cmd, str):
                _check_dangerous_patterns_in_values([script_cmd], code_injection_patterns, issues)
    
    # Check build-system for security issues
    if 'build-system' in config:
        build_deps = config['build-system'].get('requires', [])
        _check_dangerous_patterns_in_values(build_deps, code_injection_patterns, issues)
        build_backend = str(config['build-system'].get('build-backend', '')).strip()
        if not build_backend:
            issues.append("WARNING: Non-standard build backend configuration: missing build-backend field")
        elif build_backend not in {
            "setuptools.build_meta",
            "hatchling.build",
            "poetry.core.masonry.api",
            "flit_core.buildapi",
        }:
            issues.append(f"WARNING: Non-standard build backend: {build_backend}")
    
    # Check for insecure package sources (only warn, not fail)
    # This is informational for transparency
    if 'project' in config and 'urls' in config['project']:
        urls = config['project']['urls']
        # Check for potentially untrusted package sources
        untrusted_sources = []
        for key, url in urls.items():
            if url and ('github.com' not in url.lower() and 'gitlab.com' not in url.lower() 
                       and 'pypi.org' not in url.lower()):
                # This is informational only
                pass
    
    # Verify version file integrity if using dynamic versioning
    if 'project' in config and 'dynamic' in config and 'version' in config['project']['dynamic']:
        ver_exit, ver_issues = _verify_version_file_integrity(project_root)
        issues.extend(ver_issues)
        exit_code = max(exit_code, ver_exit)
    
    if any(i.startswith("SECURITY:") for i in issues):
        exit_code = 1

    return exit_code, issues


def security_check(project_root: Optional[Path] = None) -> int:
    """Run security checks on the project.
    
    This function performs comprehensive security checks including:
    - pyproject.toml validation
    - Dangerous package detection
    - Code injection pattern scanning
    - Version file integrity verification
    
    SECURITY-level issues will cause the check to fail with non-zero exit code.
    
    Args:
        project_root: Optional path to project root. If None, will search for it.
        
    Returns:
        Exit code: 0 for success, 1 for security issues detected
    """
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # Find project root if not provided
    if project_root is None:
        try:
            project_root = find_project_root()
        except RuntimeError as e:
            logger.error(f"Failed to find project root: {e}")
            return 1
    
    logger.info(f"Running security checks for: {project_root}")
    
    all_issues: list[str] = []
    exit_code = 0
    security_issues: list[str] = []
    
    # Run pyproject.toml validation
    toml_exit, toml_issues = validate_pyproject_toml(project_root)
    all_issues.extend(toml_issues)
    
    # Track SECURITY-level issues separately for proper handling
    for issue in toml_issues:
        if issue.startswith("SECURITY:"):
            security_issues.append(issue)
    
    if toml_exit != 0:
        exit_code = toml_exit
    
    # Print all issues
    if all_issues:
        logger.info("=" * 60)
        logger.info("Security Check Results:")
        logger.info("=" * 60)
        
        # Print security issues first with emphasis
        if security_issues:
            logger.error("CRITICAL SECURITY ISSUES DETECTED:")
            for issue in security_issues:
                logger.error(f"  {issue}")
            logger.info("")
        
        # Print other issues
        for issue in all_issues:
            if not issue.startswith("SECURITY:"):
                if issue.startswith("ERROR:"):
                    logger.error(f"  {issue}")
                else:
                    logger.warning(f"  {issue}")
    
    # Final verdict
    logger.info("=" * 60)
    if exit_code == 0:
        logger.info("Security check passed - no critical issues found.")
    else:
        logger.error("Security check FAILED - see issues above.")
        logger.error("Please review and fix the reported issues before continuing.")
    
    return exit_code


def run_tests(project_root: Path) -> int:
    """Run project tests using pytest.
    
    Args:
        project_root: Path to project root directory
        
    Returns:
        Exit code from pytest
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("Running tests...")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", "tests/"],
            cwd=project_root,
            capture_output=False
        )
        return result.returncode
    except Exception as e:
        logger.error(f"Failed to run tests: {e}")
        return 1


def run_format(project_root: Optional[Path] = None) -> int:
    """Format code using ruff (with auto-fix).
    
    Args:
        project_root: Optional path to project root directory
        
    Returns:
        Exit code from ruff
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    if project_root is None:
        project_root = Path.cwd()
    
    logger.info("Running code formatting (ruff check --fix)...")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--fix", "src/", "tests/"],
            cwd=project_root,
            capture_output=False
        )
        
        if result.returncode == 0:
            logger.info("Formatting completed successfully.")
        else:
            logger.warning("Formatting completed with some issues.")
        
        return result.returncode
    except Exception as e:
        logger.error(f"Failed to run formatter: {e}")
        return 1


def run_lint(project_root: Optional[Path] = None) -> int:
    """Run linting using ruff.
    
    Args:
        project_root: Optional path to project root directory
        
    Returns:
        Exit code from ruff
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    if project_root is None:
        project_root = Path.cwd()
    
    logger.info("Running linting checks...")
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "src/", "tests/"],
            cwd=project_root,
            capture_output=False
        )
        
        if result.returncode == 0:
            logger.info("Linting passed successfully.")
        else:
            logger.warning("Linting found issues.")
        
        return result.returncode
    except Exception as e:
        logger.error(f"Failed to run linter: {e}")
        return 1


def run_audit(project_root: Optional[Path] = None) -> int:
    """Run security audit tools (pip-audit and safety).
    
    This function runs both pip-audit and safety check to identify
    known vulnerabilities in project dependencies.
    
    Args:
        project_root: Optional path to project root directory
        
    Returns:
        Exit code: 0 if all checks pass, 1 otherwise
    """
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    if project_root is None:
        project_root = Path.cwd()
    
    all_exit_codes = []
    has_vulnerabilities = False
    
    # Run pip-audit
    logger.info("=" * 60)
    logger.info("Running pip-audit...")
    logger.info("=" * 60)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit"],
            cwd=project_root,
            capture_output=False
        )
        if result.returncode != 0:
            has_vulnerabilities = True
        all_exit_codes.append(result.returncode)
    except FileNotFoundError:
        logger.warning("pip-audit not found. Install with: pip install pip-audit")
    except Exception as e:
        logger.error(f"Failed to run pip-audit: {e}")
        all_exit_codes.append(1)
    
    # Run safety check
    logger.info("")
    logger.info("=" * 60)
    logger.info("Running safety check...")
    logger.info("=" * 60)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "safety", "check"],
            cwd=project_root,
            capture_output=False
        )
        if result.returncode != 0:
            has_vulnerabilities = True
        all_exit_codes.append(result.returncode)
    except FileNotFoundError:
        logger.warning("safety not found. Install with: pip install safety")
    except Exception as e:
        logger.error(f"Failed to run safety check: {e}")
        all_exit_codes.append(1)
    
    # Final verdict
    if has_vulnerabilities:
        logger.error("")
        logger.error("=" * 60)
        logger.error("SECURITY AUDIT FAILED - Vulnerabilities detected!")
        logger.error("Please review and fix the reported vulnerabilities.")
        return 1
    else:
        logger.info("")
        logger.info("=" * 60)
        logger.info("Security audit passed - no vulnerabilities detected.")
        return 0


def main():
    """Main CLI entry point with command routing."""
    parser = argparse.ArgumentParser(
        description="OPC Optimizer CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Run project tests")
    
    # Format command
    format_parser = subparsers.add_parser("format", help="Format code using ruff")
    
    # Lint command
    lint_parser = subparsers.add_parser("lint", help="Run linting checks")
    
    # Security check command
    security_parser = subparsers.add_parser("security-check", help="Run security checks")
    
    # Audit command
    audit_parser = subparsers.add_parser("audit", help="Run security audit (pip-audit + safety)")
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 0
    
    # Route commands - only security_check, audit need project root
    # Other commands can work with current directory or no specific root
    try:
        if args.command == "test":
            project_root = Path.cwd()
            return run_tests(project_root)
        elif args.command == "format":
            return run_format(Path.cwd())
        elif args.command == "lint":
            return run_lint(Path.cwd())
        elif args.command == "security-check":
            return security_check()
        elif args.command == "audit":
            return run_audit()
        else:
            parser.print_help()
            return 0
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        return 130
    except Exception as e:
        logging.error(f"Command failed: {e}")
        return 1


def webui_main():
    """Entry point for web UI (opc-webui)."""
    from opc_optimizer.ui.app import main as ui_main
    ui_main()


def skill_main():
    """Entry point for skill management (opc-skill)."""
    from opc_optimizer.cli_skills import main as skills_main
    skills_main()


if __name__ == "__main__":
    sys.exit(main())
