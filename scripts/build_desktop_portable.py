"""Build a Windows portable OPC Desktop directory with PyInstaller."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP_WEB = ROOT / "ui" / "desktop" / "web"
ENTRY = ROOT / "desktop_entry.py"


def _sep() -> str:
    return ";" if os.name == "nt" else ":"


def main() -> int:
    if not (DESKTOP_WEB / "vendor" / "three.module.js").is_file():
        print("Missing desktop Three.js asset: ui/desktop/web/vendor/three.module.js")
        return 1

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        "OPC-Desktop",
        "--onedir",
        "--clean",
        "--noconsole",
        "--add-data",
        f"{DESKTOP_WEB}{_sep()}ui/desktop/web",
        str(ENTRY),
    ]
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
