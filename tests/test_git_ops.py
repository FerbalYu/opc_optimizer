"""Tests for git operations utility."""

import os
import sys
import subprocess
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.git_ops import is_git_repo, git_init, git_auto_commit, git_diff_summary


class TestIsGitRepo:
    def test_true_for_git_dir(self, tmp_project):
        """tmp_project fixture creates .git directory."""
        assert is_git_repo(str(tmp_project)) is True

    def test_false_for_non_git_dir(self, tmp_path):
        assert is_git_repo(str(tmp_path)) is False


class TestGitInit:
    def test_returns_true_if_already_git(self, tmp_project):
        """Should return True without calling git init if .git exists."""
        result = git_init(str(tmp_project))
        assert result is True

    @patch("utils.git_ops.subprocess.run")
    def test_initializes_new_repo(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        result = git_init(str(tmp_path))
        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["git", "init"]

    @patch("utils.git_ops.subprocess.run", side_effect=FileNotFoundError("git not found"))
    def test_handles_git_not_installed(self, mock_run, tmp_path):
        result = git_init(str(tmp_path))
        assert result is False


class TestGitAutoCommit:
    def test_skips_non_git_repo(self, tmp_path):
        result = git_auto_commit(str(tmp_path), round_num=1)
        assert result is False

    @patch("utils.git_ops.subprocess.run")
    def test_stages_and_commits(self, mock_run, tmp_project):
        # First call: git add -A (success)
        # Second call: git diff --cached --quiet (returncode=1 means there are staged changes)
        # Third call: git commit (success)
        mock_run.side_effect = [
            MagicMock(returncode=0),  # git add -A
            MagicMock(returncode=1),  # git diff --cached --quiet (has changes)
            MagicMock(returncode=0),  # git commit
        ]
        result = git_auto_commit(str(tmp_project), round_num=3, summary="test changes")
        assert result is True
        assert mock_run.call_count == 3
        # Verify commit message contains round number
        commit_call = mock_run.call_args_list[2]
        commit_msg = commit_call[0][0][3]  # ["git", "commit", "-m", MSG]
        assert "Round 3" in commit_msg

    @patch("utils.git_ops.subprocess.run")
    def test_no_staged_changes_skips_commit(self, mock_run, tmp_project):
        mock_run.side_effect = [
            MagicMock(returncode=0),  # git add -A
            MagicMock(returncode=0),  # git diff --cached --quiet (no changes)
        ]
        result = git_auto_commit(str(tmp_project), round_num=1)
        assert result is True
        assert mock_run.call_count == 2  # No commit call

    @patch("utils.git_ops.subprocess.run", side_effect=FileNotFoundError("git not found"))
    def test_handles_git_not_available(self, mock_run, tmp_project):
        result = git_auto_commit(str(tmp_project), round_num=1)
        assert result is False


class TestGitDiffSummary:
    def test_returns_empty_for_non_git(self, tmp_path):
        result = git_diff_summary(str(tmp_path))
        assert result == ""

    @patch("utils.git_ops.subprocess.run")
    def test_returns_diff_stat(self, mock_run, tmp_project):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=" main.py | 2 +-\n 1 file changed, 1 insertion(+), 1 deletion(-)\n"
        )
        result = git_diff_summary(str(tmp_project))
        assert "main.py" in result
        assert "1 file changed" in result
