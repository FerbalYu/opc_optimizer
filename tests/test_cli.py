"""
Tests for CLI module, particularly validate_pyproject_toml function.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch
import re

from local_optimizer.cli import (
    validate_pyproject_toml,
    find_project_root,
    _check_dependencies,
    _get_toml_parser,
    _check_dangerous_patterns_in_values,
)


class TestValidatePyprojectToml:
    """Test cases for validate_pyproject_toml function."""
    
    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project directory."""
        return tmp_path
    
    def test_valid_pyproject(self, temp_project):
        """Test validation passes for a valid pyproject.toml."""
        pyproject_content = '''
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "test-project"
version = "0.1.0"
dependencies = [
    "requests>=2.28.0",
    "pydantic>=2.0.0",
]

[project.scripts]
test-cmd = "test_project.main:main"
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        # Should pass without errors
        assert exit_code == 0
        # Should not have ERROR level issues
        assert not any(i.startswith("ERROR:") for i in issues)
    
    def test_missing_pyproject(self, temp_project):
        """Test validation fails when pyproject.toml is missing."""
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        assert exit_code == 1
        assert any("not found" in i.lower() for i in issues)
    
    def test_dangerous_eval_pattern(self, temp_project):
        """Test detection of dangerous eval() calls."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"

[project.scripts]
bad-script = "import eval('os.system()')"
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        assert exit_code == 1
        assert any("eval" in i.lower() for i in issues)
    
    def test_dangerous_exec_pattern(self, temp_project):
        """Test detection of dangerous exec() calls."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"

[project.scripts]
bad-script = "exec('malicious code')"
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        assert exit_code == 1
        assert any("exec" in i.lower() for i in issues)
    
    def test_shell_injection_pattern(self, temp_project):
        """Test detection of shell=True in subprocess."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"

[project.scripts]
bad-script = "subprocess.run(cmd, shell=True)"
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        assert exit_code == 1
        assert any("shell" in i.lower() for i in issues)
    
    def test_os_system_pattern(self, temp_project):
        """Test detection of os.system() calls."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"

[project.scripts]
bad-script = "os.system('rm -rf /')"
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        assert exit_code == 1
        assert any("os.system" in i.lower() for i in issues)
    
    def test_wildcard_version_warning(self, temp_project):
        """Test warning for wildcard versions in dependencies."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"
dependencies = [
    "requests>=1.*",
]
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        # Should have a warning about wildcard version
        wildcard_warnings = [
            i for i in issues 
            if 'wildcard' in i.lower() and 'version' in i.lower()
        ]
        assert len(wildcard_warnings) > 0, f"Expected wildcard version warning, got: {issues}"
        assert any('requests' in i.lower() for i in wildcard_warnings)
    
    def test_wildcard_version_no_false_positive(self, temp_project):
        """Test that wildcard version warning doesn't trigger for non-wildcard versions."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"
dependencies = [
    "pick>=1.0.0",
]
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        wildcard_warnings = [
            i for i in issues 
            if 'wildcard' in i.lower() and 'version' in i.lower()
        ]
        assert len(wildcard_warnings) == 0, f"False positive wildcard warning: {issues}"
    
    def test_dangerous_script_rm_rf(self, temp_project):
        """Test detection of dangerous rm -rf in scripts."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"

[project.scripts]
bad-script = "rm -rf /tmp/test"
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        assert exit_code == 1
        assert any("rm -rf" in i.lower() for i in issues)
    
    def test_dangerous_packages_warning(self, temp_project):
        """Test warning for dangerous core packages."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"
dependencies = [
    "pip>=21.0",
    "setuptools>=61.0",
]
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        assert any("pip" in i.lower() for i in issues)
        assert any("setuptools" in i.lower() for i in issues)
    
    def test_optional_dependencies(self, temp_project):
        """Test validation of optional dependencies."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
]
security = [
    "bandit>=1.7.0",
]
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        assert exit_code == 0
    
    def test_non_standard_build_backend(self, temp_project):
        """Test info message for non-standard build backend."""
        pyproject_content = '''
[build-system]
requires = ["some-unknown-backend"]

[project]
name = "test-project"
version = "0.1.0"
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        assert any("non-standard" in i.lower() or "build backend" in i.lower() for i in issues)
    
    def test_read_error(self, temp_project):
        """Test handling of unreadable pyproject.toml."""
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text("[project]\nname = 'test'", encoding="utf-8")
        
        if os.name != 'nt':
            os.chmod(pyproject_file, 0o000)
        
        try:
            exit_code, issues = validate_pyproject_toml(temp_project)
            assert exit_code == 1
            assert any("cannot read" in i.lower() for i in issues)
        finally:
            if os.name != 'nt':
                os.chmod(pyproject_file, 0o644)
    
    def test_complex_version_constraints(self, temp_project):
        """Test handling of complex version constraints."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"
dependencies = [
    "requests>=2.28.0,<3.0.0",
    "pydantic>=2.0.0,<3.0.0",
    "numpy>=1.24.0",
]
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        assert not any("wildcard" in i.lower() for i in issues)
    
    def test_comment_no_false_positive(self, temp_project):
        """Test that comments don't trigger false positives."""
        pyproject_content = '''
# This script uses eval for testing purposes only

[project]
name = "test-project"
version = "0.1.0"

[project.scripts]
good-script = "print('hello world')"
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        security_issues = [i for i in issues if i.startswith("SECURITY:")]
        assert len(security_issues) == 0, f"False positive: {security_issues}"
    
    def test_quoted_dangerous_pattern_in_string(self, temp_project):
        """Test detection of dangerous patterns in string values."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"

[project.scripts]
dangerous-script = 'subprocess.run(cmd, shell=True, check=True)'
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        assert exit_code == 1
        assert any("shell" in i.lower() and "true" in i.lower() for i in issues)
    
    def test_popen_pattern(self, temp_project):
        """Test detection of os.popen() calls."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"

[project.scripts]
bad-script = "handle = os.popen('ls -la')"
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        assert exit_code == 1
        assert any("popen" in i.lower() for i in issues)
    
    def test_dynamic_import_pattern(self, temp_project):
        """Test detection of __import__ calls."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"

[project.scripts]
bad-script = "module = __import__('os')"
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        assert exit_code == 1
        assert any("__import__" in i.lower() or "dynamic import" in i.lower() for i in issues)
    
    def test_windows_delete_pattern(self, temp_project):
        """Test detection of dangerous Windows delete commands."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"

[project.scripts]
cleanup = "del /f /q temp\\*"
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        assert exit_code == 1
        assert any("del" in i.lower() for i in issues)
    
    def test_shell_expansion_pattern(self, temp_project):
        """Test detection of shell expansion in scripts."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"

[project.scripts]
dangerous = "format $HOME/.config"
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        exit_code, issues = validate_pyproject_toml(temp_project)
        
        assert exit_code == 1
        assert any("shell expansion" in i.lower() for i in issues)
    
    def test_returns_tuple(self, temp_project):
        """Test that validate_pyproject_toml returns a proper tuple."""
        pyproject_content = '''
[project]
name = "test-project"
version = "0.1.0"
'''
        pyproject_file = temp_project / "pyproject.toml"
        pyproject_file.write_text(pyproject_content, encoding="utf-8")
        
        result = validate_pyproject_toml(temp_project)
        
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], list)
    
    def test_check_dependencies_function(self):
        """Test the _check_dependencies helper function directly."""
        issues = []
        dangerous_pkgs = ['pick', 'pip', 'setuptools']
        
        _check_dependencies(['requests>=1.*'], dangerous_pkgs, issues)
        assert any('wildcard' in i.lower() for i in issues)
        
        issues.clear()
        _check_dependencies(['pip>=21.0'], dangerous_pkgs, issues)
        assert any('pip' in i.lower() for i in issues)
        
        issues.clear()
        _check_dependencies(['requests>=1.*'], dangerous_pkgs, issues, group_name='dev')
        wildcard_warnings = [i for i in issues if 'wildcard' in i.lower()]
        assert len(wildcard_warnings) == 0
    
    def test_check_dangerous_patterns_function(self):
        """Test the _check_dangerous_patterns_in_values helper function."""
        issues = []
        patterns = [
            (r'eval\s*\(', 'Found eval()'),
            (r'shell=True', 'Found shell=True'),
        ]
        
        values = ["some_code = 'test'", "eval('x')", "subprocess.run(cmd, shell=True)"]
        _check_dangerous_patterns_in_values(values, patterns, issues)
        
        assert any('eval' in i.lower() for i in issues)
        assert any('shell' in i.lower() for i in issues)
        
        issues.clear()
        values_with_non_strings = [123, None, "normal_code"]
        _check_dangerous_patterns_in_values(values_with_non_strings, patterns, issues)
        assert len(issues) == 0
    
    def test_get_toml_parser_function(self):
        """Test the _get_toml_parser helper function."""
        parser = _get_toml_parser()
        
        assert callable(parser)
        
        result = parser('[project]\nname = "test"')
        assert result['project']['name'] == 'test'


class TestFindProjectRoot:
    """Test cases for find_project_root function."""
    
    def test_finds_pyproject_in_current_dir(self, tmp_path, monkeypatch):
        """Test that pyproject.toml in current directory is found."""
        pyproject_file = tmp_path / "pyproject.toml"
        pyproject_file.write_text("[project]\nname = 'test'", encoding="utf-8")
        
        monkeypatch.chdir(tmp_path)
        
        root = find_project_root()
        assert root == tmp_path
    
    def test_raises_when_not_found(self, tmp_path, monkeypatch):
        """Test that RuntimeError is raised when pyproject.toml is not found."""
        monkeypatch.chdir(tmp_path)
        
        with pytest.raises(RuntimeError) as exc_info:
            find_project_root()
        
        assert "Could not find pyproject.toml" in str(exc_info.value)
    
    def test_respects_opc_project_root_env_var(self, tmp_path, monkeypatch):
        """Test that OPC_PROJECT_ROOT environment variable is respected."""
        monkeypatch.setenv('OPC_PROJECT_ROOT', str(tmp_path))
        
        root = find_project_root()
        assert root == tmp_path
