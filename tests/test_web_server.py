"""Tests for the Web UI server module (ui/web_server.py).

Tests cover the EventBus, WebSocket handler simulation,
static file handler, news fetch fallback, and config waiting.
"""

import json
import asyncio
import threading
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from io import BytesIO

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.web_server import (
    emit,
    _broadcast,
    _StaticHandler,
    wait_for_config,
    _fetch_news_sync,
    _ws_handler,
    start_server,
)
import ui.web_server as ws_mod


# ─── EventBus Tests ──────────────────────────────────────────────


class TestEmit:
    """Test the emit() function (thread-safe event push)."""

    def test_emit_no_loop_does_not_crash(self):
        """emit() should be a no-op when no event loop is running."""
        original_loop = ws_mod._loop
        ws_mod._loop = None
        try:
            # Should not raise
            emit("test_event", {"key": "value"})
        finally:
            ws_mod._loop = original_loop

    def test_emit_constructs_correct_json(self):
        """emit() should construct the correct JSON message."""
        captured = []

        async def fake_broadcast(msg):
            captured.append(json.loads(msg))

        original_loop = ws_mod._loop
        loop = asyncio.new_event_loop()
        ws_mod._loop = loop

        with patch("ui.web_server._broadcast", side_effect=fake_broadcast):
            with patch("asyncio.run_coroutine_threadsafe") as mock_rcs:
                # Capture what would be scheduled
                emit("node_start", {"node": "plan", "round": 1})

                # Verify run_coroutine_threadsafe was called
                assert mock_rcs.called
                # Check the coroutine argument
                call_args = mock_rcs.call_args
                assert call_args[0][1] is loop  # Second arg is loop

        ws_mod._loop = original_loop
        loop.close()

    def test_emit_with_none_data(self):
        """emit() should handle None data gracefully."""
        original_loop = ws_mod._loop
        ws_mod._loop = None
        try:
            emit("test_event", None)  # Should not raise
            emit("test_event")       # Should not raise
        finally:
            ws_mod._loop = original_loop


# ─── Broadcast Tests ─────────────────────────────────────────────


class TestBroadcast:
    """Test the _broadcast() async function."""

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_clients(self):
        """_broadcast should send message to all connected clients."""
        class _Client:
            def __init__(self):
                self.messages = []

            async def send(self, msg):
                self.messages.append(msg)

        ws1 = _Client()
        ws2 = _Client()
        original = ws_mod._clients[:]
        ws_mod._clients.clear()
        ws_mod._clients.extend([ws1, ws2])

        try:
            await _broadcast('{"type": "test"}')
            assert ws1.messages == ['{"type": "test"}']
            assert ws2.messages == ['{"type": "test"}']
        finally:
            ws_mod._clients.clear()
            ws_mod._clients.extend(original)

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_clients(self):
        """_broadcast should remove clients that raise exceptions."""
        class _AliveClient:
            async def send(self, _msg):
                return None

        class _DeadClient:
            async def send(self, _msg):
                raise ConnectionError("gone")

        ws_alive = _AliveClient()
        ws_dead = _DeadClient()

        original = ws_mod._clients[:]
        ws_mod._clients.clear()
        ws_mod._clients.extend([ws_alive, ws_dead])

        try:
            await _broadcast('{"type": "test"}')
            assert ws_dead not in ws_mod._clients
            assert ws_alive in ws_mod._clients
        finally:
            ws_mod._clients.clear()
            ws_mod._clients.extend(original)


# ─── Static Handler Tests ────────────────────────────────────────


class TestStaticHandler:
    """Test the _StaticHandler landing mode."""

    def test_landing_mode_flag_default(self):
        """Landing mode should default to False."""
        assert _StaticHandler._landing_mode is False

    def test_landing_mode_can_be_set(self):
        """Landing mode should be settable."""
        original = _StaticHandler._landing_mode
        try:
            _StaticHandler._landing_mode = True
            assert _StaticHandler._landing_mode is True
        finally:
            _StaticHandler._landing_mode = original


class TestStartServer:
    """Test startup wiring for the web server."""

    def test_start_server_skips_news_thread_when_disabled(self):
        created = []

        class DummyThread:
            def __init__(self, target=None, args=(), daemon=None, name=None):
                self.target = target
                self.args = args
                self.daemon = daemon
                self.name = name
                self.started = False
                created.append(self)

            def start(self):
                self.started = True

        with patch("ui.web_server.threading.Thread", DummyThread):
            http_thread, ws_thread = start_server(
                http_port=8765,
                ws_port=8766,
                open_browser=False,
                landing=True,
                fetch_news=False,
            )

        assert http_thread.name == "opc-http"
        assert ws_thread.name == "opc-ws"
        assert [thread.name for thread in created] == ["opc-http", "opc-ws"]
        assert all(thread.started for thread in created)

    def test_start_server_starts_news_thread_when_enabled(self):
        created = []

        class DummyThread:
            def __init__(self, target=None, args=(), daemon=None, name=None):
                self.target = target
                self.args = args
                self.daemon = daemon
                self.name = name
                self.started = False
                created.append(self)

            def start(self):
                self.started = True

        with patch("ui.web_server.threading.Thread", DummyThread):
            start_server(
                http_port=8765,
                ws_port=8766,
                open_browser=False,
                landing=True,
                fetch_news=True,
            )

        assert [thread.name for thread in created] == ["opc-http", "opc-ws", "opc-news"]
        assert all(thread.started for thread in created)


# ─── Config Waiting Tests ────────────────────────────────────────


class TestWaitForConfig:
    """Test the wait_for_config() blocking function."""

    def test_wait_returns_config_after_set(self):
        """wait_for_config should return once the event is set."""
        original_config = ws_mod._optimizer_config.copy()
        original_event = ws_mod._optimizer_ready

        ws_mod._optimizer_config.clear()
        ws_mod._optimizer_config.update({"path": "/test", "goal": "optimize"})
        ws_mod._optimizer_ready = threading.Event()
        ws_mod._optimizer_ready.set()

        try:
            result = wait_for_config()
            assert result["path"] == "/test"
            assert result["goal"] == "optimize"
        finally:
            ws_mod._optimizer_config.clear()
            ws_mod._optimizer_config.update(original_config)
            ws_mod._optimizer_ready = original_event

    def test_wait_returns_copy(self):
        """wait_for_config should return a copy, not the original dict."""
        original_event = ws_mod._optimizer_ready
        ws_mod._optimizer_ready = threading.Event()
        ws_mod._optimizer_ready.set()
        ws_mod._optimizer_config.update({"path": "/test"})

        try:
            result = wait_for_config()
            result["extra"] = "should not affect original"
            assert "extra" not in ws_mod._optimizer_config
        finally:
            ws_mod._optimizer_ready = original_event
            ws_mod._optimizer_config.pop("path", None)

    def test_wait_returns_skip_plan_review(self):
        """wait_for_config should preserve the skip_plan_review flag from landing config."""
        original_config = ws_mod._optimizer_config.copy()
        original_event = ws_mod._optimizer_ready

        ws_mod._optimizer_config.clear()
        ws_mod._optimizer_config.update({
            "path": "/test",
            "goal": "optimize",
            "skip_plan_review": True,
        })
        ws_mod._optimizer_ready = threading.Event()
        ws_mod._optimizer_ready.set()

        try:
            result = wait_for_config()
            assert result["skip_plan_review"] is True
        finally:
            ws_mod._optimizer_config.clear()
            ws_mod._optimizer_config.update(original_config)
            ws_mod._optimizer_ready = original_event


# ─── News Fetch Tests ────────────────────────────────────────────


class TestNewsFetch:
    """Test the _fetch_news_sync() background task."""

    def test_fetch_news_fallback_on_import_error(self):
        """Should not crash when LLMService is not available."""
        original = ws_mod._news_headlines[:]
        ws_mod._news_headlines.clear()

        with patch.dict("sys.modules", {"utils.llm": None}):
            # Should not raise
            _fetch_news_sync()

        # Headlines might be empty (fallback = no crash), that's OK
        ws_mod._news_headlines.clear()
        ws_mod._news_headlines.extend(original)


class TestConfigApi:
    """Test /api/config payload shaping."""

    def test_config_api_backfills_skip_plan_review_from_state(self):
        """Config API should expose skip_plan_review from optimizer state when landing config is empty."""
        original_config = ws_mod._optimizer_config.copy()
        original_state = dict(ws_mod._optimizer_state)

        ws_mod._optimizer_config.clear()
        ws_mod._optimizer_state.clear()
        ws_mod._optimizer_state.update({
            "current_round": 2,
            "llm_config": {"model": "openai/gpt-4o-mini"},
            "ui_preferences": {"skip_plan_review": True},
        })

        handler = object.__new__(_StaticHandler)
        handler.path = "/api/config"
        handler.wfile = BytesIO()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()

        try:
            _StaticHandler.do_GET(handler)
            body = json.loads(handler.wfile.getvalue().decode("utf-8"))
            assert body["skip_plan_review"] is True
            assert body["state_round"] == 2
            assert body["state_model"] == "openai/gpt-4o-mini"
        finally:
            ws_mod._optimizer_config.clear()
            ws_mod._optimizer_config.update(original_config)
            ws_mod._optimizer_state.clear()
            ws_mod._optimizer_state.update(original_state)

    def test_fetch_news_success(self):
        """Should store headlines when LLM returns valid data."""
        original = ws_mod._news_headlines[:]
        ws_mod._news_headlines.clear()

        mock_llm = MagicMock()
        mock_llm.generate_json.return_value = ["标题1", "标题2", "标题3"]

        with patch("utils.llm.LLMService", return_value=mock_llm):
            _fetch_news_sync()

        try:
            assert len(ws_mod._news_headlines) == 3
            assert ws_mod._news_headlines[0] == "标题1"
        finally:
            ws_mod._news_headlines.clear()
            ws_mod._news_headlines.extend(original)

    def test_fetch_news_non_list_result(self):
        """Should handle non-list LLM response gracefully."""
        original = ws_mod._news_headlines[:]
        ws_mod._news_headlines.clear()

        mock_llm = MagicMock()
        mock_llm.generate_json.return_value = {"error": "unexpected format"}

        with patch("utils.llm.LLMService", return_value=mock_llm):
            _fetch_news_sync()

        # Should not have stored anything
        assert len(ws_mod._news_headlines) == 0

        ws_mod._news_headlines.extend(original)
