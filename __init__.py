"""OPC Optimizer package.

The codebase still contains legacy absolute imports such as ``from state`` and
``from utils`` because it historically also ran directly from this directory.
Register package modules under those legacy names so package-mode execution
(``python -m opc_optimizer``) works while the import tree is migrated gradually.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType


def _alias_module(legacy_name: str, package_name: str) -> None:
    if legacy_name in sys.modules:
        return
    sys.modules[legacy_name] = importlib.import_module(package_name)


def _alias_package(legacy_name: str, package_dir: str) -> None:
    if legacy_name in sys.modules:
        return
    package_path = Path(__file__).with_name(package_dir)
    module = ModuleType(legacy_name)
    module.__file__ = str(package_path / "__init__.py")
    module.__path__ = [str(package_path)]
    module.__package__ = legacy_name
    sys.modules[legacy_name] = module


_alias_module("state", __name__ + ".state")
for _legacy_package in ("utils", "nodes", "plugins", "ui"):
    _alias_package(_legacy_package, _legacy_package)


__all__ = []
