"""OPC Optimizer package.

The codebase still contains legacy absolute imports such as ``from state`` and
``from utils`` because it historically also ran directly from this directory.
Register package modules under those legacy names so package-mode execution
(``python -m opc_optimizer``) works while the import tree is migrated gradually.
"""

from __future__ import annotations

import importlib
import sys


def _alias_module(legacy_name: str, package_name: str) -> None:
    if legacy_name in sys.modules:
        return
    sys.modules[legacy_name] = importlib.import_module(package_name)


def _alias_package(legacy_name: str, package_name: str) -> None:
    if legacy_name in sys.modules:
        return
    sys.modules[legacy_name] = importlib.import_module(package_name)


_alias_module("state", __name__ + ".state")
for _legacy_package in ("utils", "nodes", "plugins", "ui"):
    _alias_package(_legacy_package, __name__ + "." + _legacy_package)


__all__ = []
