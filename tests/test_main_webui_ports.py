"""Tests for Web UI port auto-selection in main.py."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main as main_mod


def test_resolve_web_ui_ports_prefers_requested_pair(monkeypatch):
    monkeypatch.setattr(main_mod, "_port_is_available", lambda port, host="127.0.0.1": True)
    assert main_mod._resolve_web_ui_ports(8765) == (8765, 8766)


def test_resolve_web_ui_ports_skips_occupied_default_pair(monkeypatch):
    occupied = {8765, 8766}

    def fake_available(port, host="127.0.0.1"):
        return port not in occupied

    monkeypatch.setattr(main_mod, "_port_is_available", fake_available)
    assert main_mod._resolve_web_ui_ports(8765, max_attempts=3) == (8767, 8768)
