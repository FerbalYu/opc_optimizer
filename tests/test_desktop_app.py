"""Smoke checks for the PySide6 desktop host module."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from ui.desktop.app import desktop_index_path, desktop_web_root


def test_desktop_app_points_to_packaged_index():
    index = Path(desktop_index_path())

    assert Path(desktop_web_root()).name == "web"
    assert index.is_file()
    assert index.name == "index.html"
