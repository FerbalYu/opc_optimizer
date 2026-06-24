"""PyInstaller entrypoint for OPC Desktop/package-mode execution."""

from __future__ import annotations

import os
import sys


PACKAGE_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PACKAGE_PARENT not in sys.path:
    sys.path.insert(0, PACKAGE_PARENT)

from opc_optimizer.main import main


if __name__ == "__main__":
    main()

