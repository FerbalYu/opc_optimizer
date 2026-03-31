"""Tests for YAML config loader with three-level priority merge."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.config_loader import load_config, _load_yaml_file, DEFAULT_CONFIG


class TestLoadYamlFile:
    def test_returns_empty_for_nonexistent(self):
        result = _load_yaml_file("/nonexistent/path/config.yaml")
        assert result == {}

    def test_returns_empty_when_yaml_unavailable(self, tmp_path, monkeypatch):
        """If yaml is not installed, should return empty dict."""
        import utils.config_loader as cl
        monkeypatch.setattr(cl, "HAS_YAML", False)
        cfg_file = tmp_path / "test.yaml"
        cfg_file.write_text("key: value", encoding="utf-8")
        result = _load_yaml_file(str(cfg_file))
        assert result == {}

    def test_loads_valid_yaml(self, tmp_path):
        """Skip if pyyaml not installed."""
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not installed")
        cfg_file = tmp_path / "test.yaml"
        cfg_file.write_text("goal: test\nmax_rounds: 10\n", encoding="utf-8")
        result = _load_yaml_file(str(cfg_file))
        assert result["goal"] == "test"
        assert result["max_rounds"] == 10

    def test_returns_empty_for_non_dict_yaml(self, tmp_path):
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not installed")
        cfg_file = tmp_path / "test.yaml"
        cfg_file.write_text("- item1\n- item2\n", encoding="utf-8")
        result = _load_yaml_file(str(cfg_file))
        assert result == {}


class TestLoadConfig:
    def test_defaults_only(self):
        """With no CLI args and no config files, should return defaults."""
        config = load_config(project_path="/nonexistent")
        assert config["goal"] == DEFAULT_CONFIG["goal"]
        assert config["max_rounds"] == DEFAULT_CONFIG["max_rounds"]
        assert config["dry_run"] == DEFAULT_CONFIG["dry_run"]

    def test_cli_overrides_defaults(self):
        config = load_config(
            cli_args={"goal": "性能优化", "max_rounds": 10},
            project_path="/nonexistent"
        )
        assert config["goal"] == "性能优化"
        assert config["max_rounds"] == 10

    def test_cli_none_values_ignored(self):
        """CLI args with None should not override defaults."""
        config = load_config(
            cli_args={"goal": None, "max_rounds": None},
            project_path="/nonexistent"
        )
        assert config["goal"] == DEFAULT_CONFIG["goal"]
        assert config["max_rounds"] == DEFAULT_CONFIG["max_rounds"]

    def test_cli_false_values_ignored(self):
        """CLI boolean False args should not override."""
        config = load_config(
            cli_args={"dry_run": False, "auto": False},
            project_path="/nonexistent"
        )
        assert config["dry_run"] == DEFAULT_CONFIG["dry_run"]

    def test_project_config_overrides_defaults(self, tmp_path):
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not installed")
        cfg_file = tmp_path / "opc.config.yaml"
        cfg_file.write_text("goal: 项目级目标\nmax_rounds: 8\n", encoding="utf-8")
        config = load_config(project_path=str(tmp_path))
        assert config["goal"] == "项目级目标"
        assert config["max_rounds"] == 8

    def test_cli_overrides_project_config(self, tmp_path):
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not installed")
        cfg_file = tmp_path / "opc.config.yaml"
        cfg_file.write_text("goal: 项目级目标\nmax_rounds: 8\n", encoding="utf-8")
        config = load_config(
            cli_args={"goal": "CLI目标"},
            project_path=str(tmp_path)
        )
        assert config["goal"] == "CLI目标"
        assert config["max_rounds"] == 8  # from project config

    def test_all_default_keys_present(self):
        config = load_config(project_path="/nonexistent")
        for key in DEFAULT_CONFIG:
            assert key in config, f"Missing default key: {key}"

    def test_extra_config_keys_preserved(self, tmp_path):
        """Extra keys in config files should be preserved."""
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not installed")
        cfg_file = tmp_path / "opc.config.yaml"
        cfg_file.write_text("custom_key: custom_value\n", encoding="utf-8")
        config = load_config(project_path=str(tmp_path))
        assert config["custom_key"] == "custom_value"
