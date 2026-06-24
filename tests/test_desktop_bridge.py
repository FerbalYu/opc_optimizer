"""Tests for the PySide6 Desktop QWebChannel bridge."""

import json
import threading
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from ui.desktop.bridge import DesktopBridge


def _args(**kwargs):
    base = {
        "project_path": "",
        "goal": "Improve code",
        "max_rounds": 5,
        "auto": False,
        "dry_run": False,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_initial_config_returns_cli_defaults():
    bridge = DesktopBridge(_args(project_path="D:/demo", goal="optimize", max_rounds=3))
    payload = json.loads(bridge.initialConfig())

    assert payload["ok"] is True
    assert payload["project_path"] == "D:/demo"
    assert payload["goal"] == "optimize"
    assert payload["max_rounds"] == 3


def test_start_run_invokes_runner_with_project_path(tmp_path):
    called = {}
    done = threading.Event()

    def runner(config):
        called.update(config)
        done.set()
        return {"status": "ok"}

    bridge = DesktopBridge(_args(), runner=runner)
    response = json.loads(
        bridge.startRun(json.dumps({"project_path": str(tmp_path), "goal": "fix"}))
    )

    assert response["ok"] is True
    assert done.wait(2)
    assert called["project_path"] == str(tmp_path)
    assert called["goal"] == "fix"


def test_send_command_submits_to_in_process_queue(monkeypatch):
    submitted = []

    def fake_submit(command):
        submitted.append(command)
        return command

    monkeypatch.setattr("ui.web_server.submit_user_command", fake_submit)
    bridge = DesktopBridge(_args())
    response = json.loads(bridge.sendCommand(json.dumps({"action": "continue"})))

    assert response["ok"] is True
    assert submitted == [{"action": "continue"}]


def test_forward_event_emits_qwebchannel_payload():
    bridge = DesktopBridge(_args())
    captured = []
    bridge.eventReceived.connect(captured.append)

    bridge.forwardEvent("node_start", {"node": "plan", "round": 1})

    payload = json.loads(captured[0])
    assert payload == {"type": "node_start", "data": {"node": "plan", "round": 1}}
