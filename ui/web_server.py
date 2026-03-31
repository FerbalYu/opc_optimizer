"""OPC Web UI Server 鈥?WebSocket event server + static file server.

Serves the Three.js Minecraft-style 3D visualization and pushes
real-time optimizer events via WebSocket.
"""

import os
import json
import asyncio
import logging
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Any, Dict, Optional

logger = logging.getLogger("opc.webui")

# --- Global State ------------------------------------------------
_news_headlines: list = []
_optimizer_config: dict = {}  # From landing page
_optimizer_ready = threading.Event()
_optimizer_state: dict = {}  # Reference to current state (v2.3.0)
_round_details: list = []  # Detailed round history for UI (v2.3.0)


def set_optimizer_state(state: dict):
    """Register the optimizer state dict so export API can access it."""
    global _optimizer_state
    _optimizer_state = state


# --- Global Event Bus ------------------------------------------------

_clients: list = []
_loop: Optional[asyncio.AbstractEventLoop] = None


def emit(event_type: str, data: Optional[Dict[str, Any]] = None):
    """Push an event to all connected WebSocket clients (thread-safe).

    Args:
        event_type: One of node_start, node_complete, node_error,
                    log, round_start, round_end, cost_update
        data: Event payload dict
    """
    if _loop is None or _loop.is_closed():
        return

    payload = data or {}

    # -- Store round details for later retrieval (v2.3.0) ---------
    if event_type == "round_history_update":
        _round_details.append(payload)

    message = json.dumps(
        {
            "type": event_type,
            "data": payload,
        }
    )

    # Schedule broadcast on the event loop from any thread
    try:
        asyncio.run_coroutine_threadsafe(_broadcast(message), _loop)
    except RuntimeError:
        logger.debug(f"emit: event loop closed, dropping event {event_type}")


# --- User Command Queue (v2.2.0) ------------------------------------

_user_command: Optional[Dict[str, Any]] = None
_user_command_event = threading.Event()


def wait_for_user_command(timeout: float = 300) -> Optional[Dict[str, Any]]:
    """Block until the Web UI sends a user_command, or timeout.

    Returns:
        Command dict with 'action' key, or None on timeout.
        Supported actions: continue, stop, skip, rollback, adjust_goal,
        approve_plan, replan_plan, accept_diff, reject_diff
    """
    global _user_command
    _user_command = None
    _user_command_event.clear()

    got_it = _user_command_event.wait(timeout=timeout)
    if got_it and _user_command is not None:
        cmd = _user_command
        _user_command = None
        return cmd
    return None


async def _broadcast(message: str):
    """Send message to all connected clients, remove dead ones."""
    dead = []
    for ws in _clients:
        try:
            await ws.send(message)
        except Exception as e:
            logger.debug(f"Failed to send to WebSocket client: {e}")
            dead.append(ws)
    for ws in dead:
        _clients.remove(ws)


# --- WebSocket Handler -----------------------------------------------


async def _ws_handler(websocket):
    """Handle a new WebSocket connection."""
    _clients.append(websocket)
    remote = websocket.remote_address
    logger.info(f"WebUI client connected: {remote}")

    # Send welcome + news
    await websocket.send(
        json.dumps({"type": "connected", "data": {"message": "OPC Web UI connected"}})
    )

    # Send cached news headlines
    if _news_headlines:
        await websocket.send(
            json.dumps({"type": "news_data", "data": {"headlines": _news_headlines}})
        )

    try:
        async for msg in websocket:
            try:
                cmd = json.loads(msg)
                logger.debug(f"WebUI received: {cmd}")
                # Handle start_optimization from landing page
                if cmd.get("type") == "start_optimization":
                    _optimizer_config.update(cmd.get("data", {}))
                    _optimizer_ready.set()
                    await websocket.send(
                        json.dumps(
                            {"type": "optimization_started", "data": _optimizer_config}
                        )
                    )
                # Handle user_command from interactive mode (v2.2.0)
                elif cmd.get("type") == "user_command":
                    global _user_command
                    _user_command = cmd.get("data", {})
                    _user_command_event.set()
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "command_received",
                                "data": {
                                    "action": _user_command.get("action", "unknown")
                                },
                            }
                        )
                    )
                # Handle request_history from UI (v2.3.0)
                elif cmd.get("type") == "request_history":
                    await websocket.send(
                        json.dumps(
                            {"type": "full_history", "data": {"rounds": _round_details}}
                        )
                    )
                # Handle request_traces from UI (v2.6.0)
                elif cmd.get("type") == "request_traces":
                    try:
                        from utils.trace_logger import get_trace_logger

                        round_num = cmd.get("data", {}).get("round")
                        if round_num:
                            entries = get_trace_logger().get_round(int(round_num))
                        else:
                            entries = []
                            for rnd_entries in (
                                get_trace_logger().get_all_rounds().values()
                            ):
                                entries.extend(rnd_entries)
                        await websocket.send(
                            json.dumps(
                                {"type": "trace_data", "data": {"entries": entries}}
                            )
                        )
                    except Exception as e:
                        logger.warning(f"request_traces failed: {e}")
                # Handle validate_path from landing page (v2.9.0)
                elif cmd.get("type") == "validate_path":
                    try:
                        from utils.config_template import validate_project_path

                        path = cmd.get("data", {}).get("path", "")
                        result = validate_project_path(path)
                        await websocket.send(
                            json.dumps({"type": "path_validation", "data": result})
                        )
                    except Exception as e:
                        logger.warning(f"validate_path failed: {e}")
                # Handle browse_folder from landing page
                elif cmd.get("type") == "browse_folder":

                    def _open_dialog():
                        try:
                            import tkinter as tk
                            from tkinter import filedialog
                            import asyncio

                            root = tk.Tk()
                            root.withdraw()
                            root.attributes("-topmost", 1)
                            folder = filedialog.askdirectory(
                                parent=root,
                                title="选择项目文件夹 (Select Project Folder)",
                            )
                            root.destroy()
                            if folder:
                                asyncio.run_coroutine_threadsafe(
                                    websocket.send(
                                        json.dumps(
                                            {
                                                "type": "folder_selected",
                                                "data": {"path": folder},
                                            }
                                        )
                                    ),
                                    _loop,
                                )
                        except Exception as e:
                            logger.error(f"Folder browse failed: {e}")

                    threading.Thread(target=_open_dialog, daemon=True).start()
            except json.JSONDecodeError:
                logger.debug("WebSocket received invalid JSON")
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
    finally:
        if websocket in _clients:
            _clients.remove(websocket)
        logger.info(f"WebUI client disconnected: {remote}")


# --- Static File Server ----------------------------------------------


class _StaticHandler(SimpleHTTPRequestHandler):
    """Serve files from ui/web/ directory with optional landing redirect."""

    _landing_mode = False

    def __init__(self, *args, **kwargs):
        web_dir = os.path.join(os.path.dirname(__file__), "web")
        super().__init__(*args, directory=web_dir, **kwargs)

    def _handle_landing_redirect(self) -> bool:
        """Handle landing page redirect. Returns True if handled."""
        if self._landing_mode and self.path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/landing.html")
            self.end_headers()
            return True
        return False

    def _handle_api_export_report(self) -> bool:
        """Handle /api/export-report endpoint. Returns True if handled."""
        if self.path != "/api/export-report":
            return False
        try:
            from utils.report_export import export_full_report

            report_md = export_full_report(
                _optimizer_config.get("path", "."), _optimizer_state
            )
            report_bytes = report_md.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header(
                "Content-Disposition", 'attachment; filename="opc_report.md"'
            )
            self.send_header("Content-Length", str(len(report_bytes)))
            self.end_headers()
            self.wfile.write(report_bytes)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Export failed: {e}".encode())
        return True

    def _handle_api_traces(self) -> bool:
        """Handle /api/traces and /api/traces/<round> endpoints. Returns True if handled."""
        from utils.trace_logger import get_trace_logger, TraceLogger

        if self.path == "/api/traces":
            try:
                all_rounds = get_trace_logger().get_all_rounds()
                data = json.dumps(all_rounds, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Trace load failed: {e}".encode())
            return True

        if self.path.startswith("/api/traces/"):
            try:
                round_num = int(self.path.split("/")[-1])
                entries = get_trace_logger().get_round(round_num)
                if not entries:
                    project_path = _optimizer_config.get("path", ".")
                    entries = TraceLogger.load_round(project_path, round_num)
                data = json.dumps(entries, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Trace load failed: {e}".encode())
            return True

        return False

    def _handle_api_config(self) -> bool:
        """Handle /api/config and /api/config/template endpoints. Returns True if handled."""
        import os as _os

        if self.path == "/api/config":
            try:
                cfg = dict(_optimizer_config)
                cfg["state_round"] = (
                    _optimizer_state.get("current_round", 0) if _optimizer_state else 0
                )
                cfg["state_model"] = (
                    (_optimizer_state or {}).get("llm_config", {}).get("model", "")
                )
                if "skip_plan_review" not in cfg:
                    cfg["skip_plan_review"] = bool(
                        ((_optimizer_state or {}).get("ui_preferences", {}) or {}).get(
                            "skip_plan_review", False
                        )
                    )
                cfg["formatter"] = _os.environ.get("OPC_FORMATTER", "auto")
                data = json.dumps(cfg, ensure_ascii=False, default=str).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Config API failed: {e}".encode())
            return True

        if self.path == "/api/config/template":
            try:
                from utils.config_template import generate_template

                project_path = _optimizer_config.get("path", ".")
                template = generate_template(project_path)
                data = template.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/yaml; charset=utf-8")
                self.send_header(
                    "Content-Disposition", 'attachment; filename="opc.config.yaml"'
                )
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Template generation failed: {e}".encode())
            return True

        return False

    def do_GET(self):
        """Handle GET requests with routing to handlers."""
        if self._handle_landing_redirect():
            return
        if self._handle_api_export_report():
            return
        if self._handle_api_traces():
            return
        if self._handle_api_config():
            return
        return super().do_GET()

    def log_message(self, format, *args):
        pass


def _run_http_server(port: int):
    """Run the static HTTP server in a thread."""
    try:
        server = HTTPServer(("0.0.0.0", port), _StaticHandler)
        logger.info(f"Static file server on http://localhost:{port}")
        server.serve_forever()
    except OSError as e:
        logger.error(
            f"HTTP server failed to start on port {port}. Is the port already in use? ({e})"
        )


# --- Server Startup --------------------------------------------------


def start_server(
    http_port: int = 8765,
    ws_port: int = 8766,
    open_browser: bool = True,
    landing: bool = False,
    fetch_news: bool = True,
):
    """Start the Web UI servers in background threads.

    Args:
        http_port: Port for static file server
        ws_port: Port for WebSocket event server
        open_browser: Whether to auto-open the browser
        landing: If True, redirect root to landing.html
        fetch_news: Whether to start the optional AI news background fetcher
    """
    global _loop

    # Set landing mode
    _StaticHandler._landing_mode = landing

    # Start HTTP static server thread
    http_thread = threading.Thread(
        target=_run_http_server, args=(http_port,), daemon=True, name="opc-http"
    )
    http_thread.start()

    # Start WebSocket server thread
    def _run_ws():
        global _loop

        async def _ws_main():
            global _loop
            _loop = asyncio.get_running_loop()

            import websockets  # type: ignore

            try:
                async with websockets.serve(_ws_handler, "0.0.0.0", ws_port):
                    logger.info(f"WebSocket server on ws://localhost:{ws_port}")
                    await asyncio.Future()  # run forever
            except OSError as e:
                logger.error(
                    f"WebSocket server failed to start on port {ws_port}. Is the port already in use? ({e})"
                )

        try:
            asyncio.run(_ws_main())
        except Exception as e:
            logger.error(f"WebSocket thread crashed: {e}")

    ws_thread = threading.Thread(target=_run_ws, daemon=True, name="opc-ws")
    ws_thread.start()

    if fetch_news:
        news_thread = threading.Thread(
            target=_fetch_news_sync, daemon=True, name="opc-news"
        )
        news_thread.start()

    # Open browser
    if open_browser:
        import webbrowser
        import time

        time.sleep(0.5)
        url = f"http://localhost:{http_port}"
        webbrowser.open(url)
        logger.info(f"Browser opened: {url}")

    return http_thread, ws_thread


def wait_for_config() -> dict:
    """Block until the landing page sends start_optimization.

    Returns:
        Config dict with 'path' and 'goal' keys.
    """
    _optimizer_ready.clear()
    _optimizer_ready.wait()
    return _optimizer_config.copy()


def _fetch_news_sync(timeout_seconds: float = 30.0):
    """Fetch AI news headlines via LLM without blocking startup indefinitely."""
    global _news_headlines
    result_holder = {"headlines": None, "error": None}

    def _worker():
        try:
            from utils.llm import LLMService

            llm = LLMService()
            result_holder["headlines"] = llm.generate_json(
                messages=[
                    {
                        "role": "system",
                        "content": "You write short Chinese AI news headlines for a dashboard ticker.",
                    },
                    {
                        "role": "user",
                        "content": (
                            "Generate 30 short Chinese AI headlines or playful AI one-liners. "
                            'Keep each item under 15 Chinese characters. Return JSON array format only, like ["headline 1", "headline 2"].'
                        ),
                    },
                ],
            )
        except Exception as exc:
            result_holder["error"] = exc

    worker = threading.Thread(target=_worker, daemon=True, name="opc-news-fetch")
    worker.start()
    worker.join(timeout=max(0.1, float(timeout_seconds)))

    if worker.is_alive():
        logger.warning(
            f"AI news fetch timed out after {timeout_seconds:.0f}s; skipping optional headlines"
        )
        return

    if result_holder["error"] is not None:
        logger.warning(f"Failed to fetch news: {result_holder['error']}")
        return

    result = result_holder["headlines"]
    if isinstance(result, list) and len(result) > 0:
        _news_headlines = result[:30]
        logger.info(f"Fetched {len(_news_headlines)} news headlines")
        emit("news_data", {"headlines": _news_headlines})
