"""Static checks for desktop portable packaging."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_desktop_packaging_script_declares_portable_assets():
    script = (ROOT / "scripts" / "build_desktop_portable.py").read_text(
        encoding="utf-8"
    )

    assert "PyInstaller" in script
    assert "--onedir" in script
    assert "three.module.js" in script
    assert "ui/desktop/web" in script


def test_desktop_requirements_include_pyside_and_packager():
    req = (ROOT / "requirements-desktop.txt").read_text(encoding="utf-8")

    assert "PySide6" in req
    assert "pyinstaller" in req.lower()

