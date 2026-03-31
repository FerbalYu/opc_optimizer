import os
import pytest
from utils.file_ops import read_file, write_to_file, append_to_file, get_project_files


class TestReadFile:
    def test_read_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        assert read_file(str(f)) == "hello world"
    
    def test_read_nonexistent_file(self):
        assert read_file("/nonexistent/file.txt") == ""
    
    def test_read_file_truncation(self, large_file):
        content = read_file(str(large_file), max_size=1000)
        assert len(content) < 2000
        assert "TRUNCATED" in content
    
    def test_read_file_no_truncation(self, tmp_path):
        f = tmp_path / "small.txt"
        f.write_text("small content", encoding="utf-8")
        content = read_file(str(f))
        assert content == "small content"
        assert "TRUNCATED" not in content


class TestWriteToFile:
    def test_write_creates_file(self, tmp_path):
        fp = str(tmp_path / "new.txt")
        write_to_file(fp, "new content")
        assert os.path.exists(fp)
        with open(fp, 'r', encoding='utf-8') as f:
            assert f.read() == "new content"
    
    def test_write_creates_directories(self, tmp_path):
        fp = str(tmp_path / "sub" / "dir" / "file.txt")
        write_to_file(fp, "nested")
        assert os.path.exists(fp)
    
    def test_write_overwrites_existing(self, tmp_path):
        fp = str(tmp_path / "existing.txt")
        write_to_file(fp, "first")
        write_to_file(fp, "second")
        with open(fp, 'r', encoding='utf-8') as f:
            assert f.read() == "second"


class TestAppendToFile:
    def test_append_to_existing(self, tmp_path):
        fp = str(tmp_path / "log.txt")
        write_to_file(fp, "line1\n")
        append_to_file(fp, "line2\n")
        with open(fp, 'r', encoding='utf-8') as f:
            assert f.read() == "line1\nline2\n"
    
    def test_append_creates_new(self, tmp_path):
        fp = str(tmp_path / "new_log.txt")
        append_to_file(fp, "first line\n")
        assert os.path.exists(fp)


class TestGetProjectFiles:
    def test_basic_discovery(self, tmp_project):
        files = get_project_files(str(tmp_project))
        basenames = [os.path.basename(f) for f in files]
        assert "main.py" in basenames
        assert "utils.py" in basenames
        assert "helper.py" in basenames
        assert "README.md" in basenames
    
    def test_ignores_git_dir(self, tmp_project):
        files = get_project_files(str(tmp_project))
        for f in files:
            assert ".git" not in f
    
    def test_ignores_pycache(self, tmp_project):
        files = get_project_files(str(tmp_project))
        for f in files:
            assert "__pycache__" not in f
    
    def test_ignores_log_dir(self, tmp_project):
        files = get_project_files(str(tmp_project))
        for f in files:
            assert ".opclog" not in f
    
    def test_extension_filter(self, tmp_project):
        py_files = get_project_files(str(tmp_project), extensions=[".py"])
        for f in py_files:
            assert f.endswith(".py")
        assert len(py_files) == 3  # main.py, utils.py, helper.py
    
    def test_ignores_bak_files(self, tmp_project):
        # Create a .bak file
        (tmp_project / "main.py.bak").write_text("backup", encoding="utf-8")
        files = get_project_files(str(tmp_project))
        for f in files:
            assert not f.endswith(".bak")
    
    def test_ignores_env_files(self, tmp_project):
        (tmp_project / ".env").write_text("SECRET=x", encoding="utf-8")
        files = get_project_files(str(tmp_project))
        for f in files:
            assert not f.endswith(".env")
