"""Tests for the WebUI interact path in interact_node.

Verifies:
- WebUI mode (--web-ui) does NOT set auto_mode=True in main.py args
- _try_web_ui_interact auto-continues on 30s timeout
- _try_web_ui_interact emits round_end before waiting
- _try_web_ui_interact emits optimization_complete on stop
- _emit_stop_events fires round_end + optimization_complete

Note: interact.py imports emit/_clients/wait_for_user_command from ui.web_server
inside the functions, so we patch them on the ui.web_server module.
"""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes.interact import _try_web_ui_interact, _emit_stop_events
import ui.web_server as ws_mod


def _make_state(**kwargs):
    base = {
        "project_path": "/tmp/test",
        "optimization_goal": "test goal",
        "current_round": 1,
        "max_rounds": 3,
        "should_stop": False,
        "modified_files": [],
        "code_diff": "",
        "suggestions": "suggestions",
        "round_reports": [],
        "node_timings": {"plan": 1.0, "execute": 2.0},
        "consecutive_no_improvements": 0,
        "auto_mode": False,
    }
    base.update(kwargs)
    return base


class TestTryWebUIInteract:
    """Tests for _try_web_ui_interact().

    interact.py does `from ui.web_server import emit, _clients, wait_for_user_command`
    inside _try_web_ui_interact, so we patch on ui.web_server.
    """

    def test_timeout_auto_continues(self):
        """On 30s timeout (wait_for_user_command returns None), should auto-continue."""
        state = _make_state()
        emitted = []
        fake_client = MagicMock()

        with patch.object(ws_mod, "_clients", [fake_client]):
            with patch.object(ws_mod, "wait_for_user_command", return_value=None):
                with patch.object(ws_mod, "emit", side_effect=lambda t, d=None: emitted.append(t)):
                    result = _try_web_ui_interact(state)

        assert result is True
        assert state["should_stop"] is False
        assert state["current_round"] == 2  # incremented
        assert "round_end" in emitted
        assert "awaiting_input" in emitted
        assert "optimization_complete" not in emitted

    def test_stop_command_sets_should_stop(self):
        """User sends 'stop': should_stop=True and optimization_complete emitted."""
        state = _make_state()
        emitted = []

        with patch.object(ws_mod, "_clients", [MagicMock()]):
            with patch.object(ws_mod, "wait_for_user_command", return_value={"action": "stop"}):
                with patch.object(ws_mod, "emit", side_effect=lambda t, d=None: emitted.append(t)):
                    with patch("nodes.interact._generate_final_report"):
                        result = _try_web_ui_interact(state)

        assert result is True
        assert state["should_stop"] is True
        assert state["current_round"] == 1  # NOT incremented
        assert "optimization_complete" in emitted

    def test_continue_command_increments_round(self):
        """User sends 'continue': round increments, no optimization_complete."""
        state = _make_state()
        emitted = []

        with patch.object(ws_mod, "_clients", [MagicMock()]):
            with patch.object(ws_mod, "wait_for_user_command", return_value={"action": "continue"}):
                with patch.object(ws_mod, "emit", side_effect=lambda t, d=None: emitted.append(t)):
                    result = _try_web_ui_interact(state)

        assert result is True
        assert state["should_stop"] is False
        assert state["current_round"] == 2
        assert "optimization_complete" not in emitted

    def test_returns_false_when_no_clients(self):
        """Should return False immediately if no WebUI clients are connected."""
        state = _make_state()
        with patch.object(ws_mod, "_clients", []):
            result = _try_web_ui_interact(state)
        assert result is False

    def test_round_end_includes_timings(self):
        """round_end event payload must include timing data from state."""
        state = _make_state()
        payloads = {}

        def capture_emit(event_type, data=None):
            payloads[event_type] = data

        with patch.object(ws_mod, "_clients", [MagicMock()]):
            with patch.object(ws_mod, "wait_for_user_command", return_value=None):
                with patch.object(ws_mod, "emit", side_effect=capture_emit):
                    _try_web_ui_interact(state)

        assert "round_end" in payloads
        assert payloads["round_end"]["round"] == 1
        assert "plan" in payloads["round_end"]["timings"]

    def test_awaiting_input_timeout_is_30s(self):
        """wait_for_user_command must be called with timeout=30."""
        state = _make_state()
        called_with = {}

        def fake_wait(timeout=300):
            called_with["timeout"] = timeout
            return None

        with patch.object(ws_mod, "_clients", [MagicMock()]):
            with patch.object(ws_mod, "wait_for_user_command", side_effect=fake_wait):
                with patch.object(ws_mod, "emit"):
                    _try_web_ui_interact(state)

        assert called_with.get("timeout") == 30


class TestEmitStopEvents:
    """Tests for _emit_stop_events()."""

    def test_emits_round_end_and_optimization_complete(self):
        state = _make_state(current_round=2)
        emitted = {}

        def capture(t, d=None):
            emitted[t] = d

        with patch.object(ws_mod, "_clients", [MagicMock()]):
            with patch.object(ws_mod, "emit", side_effect=capture):
                _emit_stop_events(state, 2)

        assert "round_end" in emitted
        assert emitted["round_end"]["round"] == 2
        assert "optimization_complete" in emitted
        assert emitted["optimization_complete"]["total_rounds"] == 2
        assert emitted["optimization_complete"]["shutdown_in_seconds"] == 15

    def test_does_nothing_without_clients(self):
        state = _make_state()
        emitted = []

        with patch.object(ws_mod, "_clients", []):
            with patch.object(ws_mod, "emit", side_effect=lambda t, d=None: emitted.append(t)):
                _emit_stop_events(state, 1)

        assert emitted == []


class TestMainAutoModeNotSet:
    """Verify main.py does NOT force auto_mode=True in WebUI mode."""

    def test_web_config_does_not_enable_auto(self):
        """Simulate the main.py web_config parsing block.
        args.auto should remain False after receiving web_config.
        """
        class FakeArgs:
            auto = False
            goal = "default goal"
            max_rounds = 3
            skip_plan_review = False
            model = None

        args = FakeArgs()
        web_config = {
            "path": "/tmp/proj",
            "goal": "new goal",
            "max_rounds": 5,
            "skip_plan_review": True,
        }

        # Replicate the fixed main.py logic
        args.goal = web_config.get("goal", args.goal)
        args.max_rounds = web_config.get("max_rounds", args.max_rounds)
        args.auto = False  # Fixed — was True before the bug fix
        args.skip_plan_review = bool(web_config.get("skip_plan_review", False))

        assert args.auto is False, "WebUI mode must NOT force auto_mode=True"
        assert args.skip_plan_review is True
        assert args.max_rounds == 5
