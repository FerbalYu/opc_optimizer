"""Smoke checks for the PySide6 desktop host module."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from ui.desktop.app import DesktopMainWindow, desktop_index_path, desktop_web_root


def test_desktop_app_points_to_packaged_index():
    index = Path(desktop_index_path())

    assert Path(desktop_web_root()).name == "web"
    assert index.is_file()
    assert index.name == "index.html"


def test_desktop_devtools_is_off_by_default(qtbot):
    window = DesktopMainWindow(type("Args", (), {"desktop_devtools": False})())
    qtbot.addWidget(window)

    assert window.devtools_view is None
