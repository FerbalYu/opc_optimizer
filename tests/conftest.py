import os
import sys
import pytest
import tempfile
import shutil

# Add the project root to sys.path so tests can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with sample files."""
    # Create some sample project files
    (tmp_path / "main.py").write_text("def hello():\n    print('hello')\n", encoding="utf-8")
    (tmp_path / "utils.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Test Project\n", encoding="utf-8")
    
    # Create directories that should be ignored
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"")
    
    # Create a nested directory
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "helper.py").write_text("x = 1\n", encoding="utf-8")
    
    # Create log directory
    (tmp_path / ".opclog").mkdir()
    
    return tmp_path


@pytest.fixture
def large_file(tmp_path):
    """Create a file exceeding the default max_size."""
    large = tmp_path / "large.txt"
    large.write_text("x" * 600_000, encoding="utf-8")
    return large
