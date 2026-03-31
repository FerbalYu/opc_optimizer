import os
import shutil
import pytest
from nodes.execute import (
    _read_target_files,
    _apply_modification,
    _filter_modifications_to_contract,
    _get_execute_allowed_paths,
)
from utils.file_ops import write_to_file


class TestReadTargetFiles:
    def test_prefers_round_contract_target_files(self, tmp_project):
        (tmp_project / "extra.py").write_text("y = 2", encoding="utf-8")
        plan = "We should modify main.py to improve performance"
        contract = {"target_files": ["extra.py"]}
        result = _read_target_files(str(tmp_project), plan, round_contract=contract)
        assert list(result.keys()) == ["extra.py"]

    def test_reads_mentioned_files(self, tmp_project):
        plan = "We should modify main.py to improve performance"
        result = _read_target_files(str(tmp_project), plan)
        # main.py should be found since it's mentioned in the plan
        keys = list(result.keys())
        found = any("main.py" in k for k in keys)
        assert found, f"main.py not found in keys: {keys}"
    
    def test_falls_back_to_all_files(self, tmp_project):
        plan = "General optimization of the project"
        result = _read_target_files(str(tmp_project), plan)
        # Should find some files even if none are explicitly mentioned
        assert len(result) > 0
    
    def test_respects_max_files_limit(self, tmp_project):
        # Create 20 files
        for i in range(20):
            (tmp_project / f"file_{i}.py").write_text(f"x = {i}", encoding="utf-8")
        plan = "General optimization"
        result = _read_target_files(str(tmp_project), plan)
        assert len(result) <= 15
    
    def test_truncates_large_files(self, tmp_project):
        (tmp_project / "big.py").write_text("x = 1\n" * 1000, encoding="utf-8")
        plan = "modify big.py"
        result = _read_target_files(str(tmp_project), plan)
        big_content = [v for k, v in result.items() if "big.py" in k]
        if big_content:
            assert len(big_content[0]) <= 5000


class TestFilterModificationsToContract:
    def test_marks_no_change_files_as_read_only_for_execute(self):
        contract = {
            "target_files": ["utils/flying-stars.js", "pages/flying-stars/flying-stars.js"],
            "expected_diff": [
                "In utils/flying-stars.js: No changes needed - verify only",
                "In pages/flying-stars/flying-stars.js: Merge consecutive setData calls",
            ],
        }

        allowed = _get_execute_allowed_paths(contract, contract["target_files"])

        assert allowed == ["pages/flying-stars/flying-stars.js"]

    def test_keeps_only_allowed_contract_files(self):
        modifications = [
            {"filepath": "main.py", "old_content_snippet": "a", "new_content": "b", "reason": "keep"},
            {"filepath": "extra.py", "old_content_snippet": "x", "new_content": "y", "reason": "drop"},
        ]
        contract = {"target_files": ["main.py"]}

        kept, rejected = _filter_modifications_to_contract(modifications, contract)

        assert len(kept) == 1
        assert kept[0]["filepath"] == "main.py"
        assert len(rejected) == 1
        assert "extra.py" in rejected[0]

    def test_allows_all_modifications_without_contract_targets(self):
        modifications = [
            {"filepath": "main.py", "old_content_snippet": "a", "new_content": "b", "reason": "keep"},
        ]

        kept, rejected = _filter_modifications_to_contract(modifications, {})

        assert kept == modifications
        assert rejected == []

    def test_filters_out_read_only_target_files(self):
        modifications = [
            {"filepath": "utils/flying-stars.js", "old_content_snippet": "a", "new_content": "b", "reason": "drop"},
            {"filepath": "pages/flying-stars/flying-stars.js", "old_content_snippet": "x", "new_content": "y", "reason": "keep"},
        ]
        contract = {
            "target_files": ["utils/flying-stars.js", "pages/flying-stars/flying-stars.js"],
            "expected_diff": [
                "In utils/flying-stars.js: No changes needed - verify only",
            ],
        }
        allowed = _get_execute_allowed_paths(contract, contract["target_files"])

        kept, rejected = _filter_modifications_to_contract(modifications, contract, allowed_paths=allowed)

        assert len(kept) == 1
        assert kept[0]["filepath"] == "pages/flying-stars/flying-stars.js"
        assert len(rejected) == 1
        assert "utils/flying-stars.js" in rejected[0]


class TestApplyModification:
    def test_successful_modification(self, tmp_project):
        mod = {
            "filepath": "main.py",
            "old_content_snippet": "def hello():",
            "new_content": "def hello_world():",
            "reason": "Better naming"
        }
        result = _apply_modification(str(tmp_project), mod)
        assert result.startswith("MODIFIED")
        # Verify the file was actually changed
        with open(tmp_project / "main.py", 'r', encoding='utf-8') as f:
            assert "def hello_world():" in f.read()
        # Verify backup was created
        assert (tmp_project / "main.py.bak").exists()
    
    def test_dry_run_no_modification(self, tmp_project):
        mod = {
            "filepath": "main.py",
            "old_content_snippet": "def hello():",
            "new_content": "def hello_dry():",
            "reason": "Dry run test"
        }
        result = _apply_modification(str(tmp_project), mod, dry_run=True)
        assert result.startswith("DRY-RUN")
        # File should NOT be changed
        with open(tmp_project / "main.py", 'r', encoding='utf-8') as f:
            assert "def hello():" in f.read()
    
    def test_file_not_found(self, tmp_project):
        mod = {
            "filepath": "nonexistent.py",
            "old_content_snippet": "x",
            "new_content": "y",
            "reason": "test"
        }
        result = _apply_modification(str(tmp_project), mod)
        assert result.startswith("SKIP")
        assert "file not found" in result
    
    def test_snippet_not_found(self, tmp_project):
        mod = {
            "filepath": "main.py",
            "old_content_snippet": "THIS DOES NOT EXIST",
            "new_content": "replacement",
            "reason": "test"
        }
        result = _apply_modification(str(tmp_project), mod)
        assert result.startswith("SKIP")
        assert "no matching code found" in result or "not found" in result
    
    def test_path_traversal_blocked(self, tmp_project):
        mod = {
            "filepath": "../../etc/passwd",
            "old_content_snippet": "root",
            "new_content": "hacked",
            "reason": "evil"
        }
        result = _apply_modification(str(tmp_project), mod)
        assert result.startswith("BLOCKED")
    
    def test_absolute_path_blocked(self, tmp_project):
        mod = {
            "filepath": "/etc/passwd",
            "old_content_snippet": "root",
            "new_content": "hacked",
            "reason": "evil"
        }
        result = _apply_modification(str(tmp_project), mod)
        assert result.startswith("BLOCKED")
    
    def test_no_snippet_provided(self, tmp_project):
        mod = {
            "filepath": "main.py",
            "old_content_snippet": "",
            "new_content": "something",
            "reason": "test"
        }
        result = _apply_modification(str(tmp_project), mod)
        assert result.startswith("SKIP")
        assert "no old_content_snippet" in result
