"""Regression tests for package-mode execution."""

import os
import subprocess
import sys


PACKAGE_PARENT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_package_graph_import_from_parent_directory():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import opc_optimizer; import opc_optimizer.graph; print('ok')",
        ],
        cwd=PACKAGE_PARENT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_python_m_opc_optimizer_help_from_parent_directory():
    result = subprocess.run(
        [sys.executable, "-m", "opc_optimizer", "--help"],
        cwd=PACKAGE_PARENT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "OPC Local Code Optimizer" in result.stdout
    assert "--web-ui" in result.stdout
