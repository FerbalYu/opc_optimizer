"""YAML configuration loader with four-level priority merge.

Priority: CLI args > environment variables > project opc.config.yaml > global ~/.opc/config.yaml > defaults
"""

import os
import logging
from typing import Any, Dict, Optional

try:
    from pydantic import BaseModel, Field, field_validator

    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

logger = logging.getLogger("opc.config")

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# Default configuration values
DEFAULT_CONFIG: Dict[str, Any] = {
    "goal": "Improve code quality, performance, and architecture",
    "max_rounds": 5,
    "archive_every": 3,
    "dry_run": False,
    "auto": False,
    "model": None,
    "timeout": 120,
    "log_level": "INFO",
    "build_timeout": 120,
    "max_file_size": 512000,
    "allowed_extensions": [
        ".py",
        ".js",
        ".ts",
        ".java",
        ".kt",
        ".go",
        ".rs",
        ".c",
        ".cpp",
        ".h",
    ],
}

ENV_VAR_MAP = {
    "OPC_GOAL": "goal",
    "OPC_MAX_ROUNDS": "max_rounds",
    "OPC_ARCHIVE_EVERY": "archive_every",
    "OPC_DRY_RUN": "dry_run",
    "OPC_AUTO": "auto",
    "OPC_MODEL": "model",
    "OPC_TIMEOUT": "timeout",
    "OPC_LOG_LEVEL": "log_level",
    "OPC_BUILD_TIMEOUT": "build_timeout",
}

CLI_KEY_MAP = {
    "goal": "goal",
    "max_rounds": "max_rounds",
    "archive_every": "archive_every",
    "dry_run": "dry_run",
    "auto": "auto",
    "model": "model",
    "timeout": "timeout",
}


if HAS_PYDANTIC:

    class OPCConfigModel(BaseModel):
        goal: str = Field(default="Improve code quality, performance, and architecture")
        max_rounds: int = Field(default=5, ge=1, le=100)
        archive_every: int = Field(default=3, ge=1)
        dry_run: bool = Field(default=False)
        auto: bool = Field(default=False)
        model: Optional[str] = Field(default=None)
        timeout: int = Field(default=120, ge=10, le=600)
        log_level: str = Field(default="INFO")
        build_timeout: int = Field(default=120, ge=10, le=600)
        max_file_size: int = Field(default=512000, ge=1000)
        allowed_extensions: list = Field(
            default_factory=lambda: [
                ".py",
                ".js",
                ".ts",
                ".java",
                ".kt",
                ".go",
                ".rs",
                ".c",
                ".cpp",
                ".h",
            ]
        )

        @field_validator("log_level")
        @classmethod
        def validate_log_level(cls, v: str) -> str:
            valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
            if v.upper() not in valid_levels:
                return "INFO"
            return v.upper()

        @field_validator("dry_run", "auto", mode="before")
        @classmethod
        def coerce_bool(cls, v: Any) -> bool:
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                return v.lower() in ("true", "1", "yes", "on")
            return bool(v)


def _load_yaml_file(path: str) -> Dict[str, Any]:
    """Load a YAML config file. Returns empty dict if not found or yaml unavailable."""
    if not HAS_YAML:
        return {}
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            logger.info(f"Loaded config from: {path}")
            return data
        return {}
    except Exception as e:
        logger.warning(f"Failed to load config from {path}: {e}")
        return {}


def _load_yaml_file(path: str) -> Dict[str, Any]:
    """Load a YAML config file. Returns empty dict if not found or yaml unavailable."""
    if not HAS_YAML:
        return {}
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            logger.info(f"Loaded config from: {path}")
            return data
        return {}
    except Exception as e:
        logger.warning(f"Failed to load config from {path}: {e}")
        return {}


def _load_env_vars() -> Dict[str, Any]:
    """Load configuration from environment variables (OPC_* prefix)."""
    env_config = {}
    for env_key, config_key in ENV_VAR_MAP.items():
        value = os.environ.get(env_key)
        if value is not None:
            if config_key in ("dry_run", "auto"):
                env_config[config_key] = value.lower() in ("true", "1", "yes", "on")
            elif config_key in (
                "max_rounds",
                "archive_every",
                "timeout",
                "build_timeout",
                "max_file_size",
            ):
                try:
                    env_config[config_key] = int(value)
                except ValueError:
                    logger.warning(f"Invalid integer value for {env_key}: {value}")
                    continue
            else:
                env_config[config_key] = value
            logger.debug(
                f"Loaded config from env {env_key}: {config_key}={env_config[config_key]}"
            )
    return env_config


def _validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize configuration using Pydantic if available."""
    if not HAS_PYDANTIC:
        return config

    int_fields = {
        "max_rounds": (1, 100),
        "archive_every": (1, None),
        "timeout": (10, 600),
        "build_timeout": (10, 600),
        "max_file_size": (1000, None),
    }

    validated_data = {}
    for key, value in config.items():
        if key in int_fields and isinstance(value, (int, str)):
            try:
                v = int(value) if not isinstance(value, int) else value
                min_val, max_val = int_fields[key]
                if min_val is not None and v < min_val:
                    v = min_val
                if max_val is not None and v > max_val:
                    v = max_val
                validated_data[key] = v
            except (ValueError, TypeError):
                validated_data[key] = DEFAULT_CONFIG.get(key, value)
        elif key == "log_level" and isinstance(value, str):
            validated_data[key] = (
                value.upper()
                if value.upper() in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
                else "INFO"
            )
        elif key in ("dry_run", "auto"):
            if isinstance(value, bool):
                validated_data[key] = value
            elif isinstance(value, str):
                validated_data[key] = value.lower() in ("true", "1", "yes", "on")
            else:
                validated_data[key] = bool(value)
        else:
            validated_data[key] = value

    return validated_data


def load_config(
    cli_args: Optional[Dict[str, Any]] = None,
    project_path: str = ".",
) -> Dict[str, Any]:
    """Merge configuration from four sources.

    Priority (highest to lowest):
    1. CLI arguments (non-None values only)
    2. Environment variables (OPC_* prefix)
    3. Project-level opc.config.yaml
    4. Global ~/.opc/config.yaml
    5. DEFAULT_CONFIG

    Returns merged config dict with Pydantic validation.
    """
    config = dict(DEFAULT_CONFIG)

    global_path = os.path.join(os.path.expanduser("~"), ".opc", "config.yaml")
    global_cfg = _load_yaml_file(global_path)
    config.update({k: v for k, v in global_cfg.items() if v is not None})

    project_cfg_path = os.path.join(project_path, "opc.config.yaml")
    project_cfg = _load_yaml_file(project_cfg_path)
    config.update({k: v for k, v in project_cfg.items() if v is not None})

    env_config = _load_env_vars()
    config.update(env_config)

    if cli_args:
        for key, value in cli_args.items():
            if value is not None and value is not False:
                config[key] = value

    return _validate_config(config)
