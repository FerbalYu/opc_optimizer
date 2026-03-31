import os
import sys
import argparse
import signal
import logging
import socket
import time

from state import OptimizerConfig
from utils.llm import LLMService
from utils.constants import DEFAULT_WEB_UI_HTTP_PORT, MAX_PORT_SCAN_ATTEMPTS


def _setup_gitignore(project_path: str) -> None:
    """Setup .gitignore for OPC log files."""
    gitignore_path = os.path.join(project_path, ".gitignore")
    if gitignore_path == os.path.normpath(os.path.join(project_path, ".gitignore")):
        if os.path.isfile(gitignore_path):
            with open(gitignore_path, "r", encoding="utf-8") as f:
                content = f.read()
            if ".opclog" not in content:
                with open(gitignore_path, "a", encoding="utf-8") as f:
                    f.write("\n# OPC optimizer logs\n.opclog/\n")


def _prepare_initial_state(
    config: "OptimizerConfig", run_args, llm_config: dict, tui
) -> dict:
    """Prepare initial state for optimizer graph execution."""
    initial_state = None
    if getattr(run_args, "resume", False):
        try:
            from utils.checkpoint import load_checkpoint

            initial_state = load_checkpoint(config.project_path)
            if initial_state:
                print(
                    f"🔄 Resumed from checkpoint: Round {initial_state.get('current_round', '?')}"
                )
                initial_state["auto_mode"] = run_args.auto
                initial_state["dry_run"] = run_args.dry_run
                initial_state["should_stop"] = False
                initial_state["llm_config"] = llm_config
                initial_state.setdefault("active_tasks", [])
                initial_state.setdefault("ui_preferences", {"skip_plan_review": False})
        except Exception as e:
            logging.debug(f"Failed to load checkpoint: {e}")

    if initial_state is None:
        initial_state = {
            "project_path": config.project_path,
            "optimization_goal": config.optimization_goal,
            "current_round": 1,
            "max_rounds": config.max_rounds,
            "archive_every_n_rounds": config.archive_every_n_rounds,
            "consecutive_no_improvements": 0,
            "suggestions": "",
            "current_plan": "",
            "round_contract": {},
            "round_evaluation": {},
            "active_tasks": [],
            "code_diff": "",
            "test_results": "",
            "should_stop": False,
            "round_reports": [],
            "execution_errors": [],
            "modified_files": [],
            "auto_mode": run_args.auto,
            "dry_run": run_args.dry_run,
            "llm_config": llm_config,
            "ui_preferences": {
                "skip_plan_review": bool(getattr(run_args, "skip_plan_review", False)),
            },
            "node_timings": {},
            "round_history": [],
            "build_result": {},
        }
    return initial_state


def _stream_graph_events(app, initial_state: dict, tui) -> dict:
    """Stream graph events and update state."""
    latest_state = initial_state
    for event in app.stream(initial_state):
        for k, v in event.items():
            tui.print_phase(f"Completed: {k}", "✔")
            latest_state = v
            try:
                from ui.web_server import set_optimizer_state

                set_optimizer_state(v)
            except Exception as e:
                logging.debug(f"Failed to update web UI state: {e}")
    return latest_state


def _configure_logging(level: str = "INFO") -> None:
    """Configure logging for OPC.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
    """
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Suppress noisy third-party loggers
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _configure_stdio() -> None:
    """Make redirected stdout/stderr tolerant of Unicode on Windows."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass


def _port_is_available(port: int, host: str = "127.0.0.1") -> bool:
    """Return True when a TCP port can be bound on the local machine."""
    if port <= 0 or port > 65535:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _resolve_web_ui_ports(
    preferred_http_port: int = DEFAULT_WEB_UI_HTTP_PORT, max_attempts: int = 100
) -> tuple[int, int]:
    """Find an available HTTP/WS port pair for the Web UI."""
    http_port = preferred_http_port or DEFAULT_WEB_UI_HTTP_PORT
    if http_port <= 0:
        http_port = DEFAULT_WEB_UI_HTTP_PORT
    if http_port % 2 == 0:
        http_port += 1

    for _ in range(max_attempts):
        ws_port = http_port + 1
        if _port_is_available(http_port) and _port_is_available(ws_port):
            return http_port, ws_port
        http_port += 2

    raise RuntimeError(
        f"Could not find a free Web UI port pair after {max_attempts} attempts starting from {preferred_http_port}"
    )


def _keep_webui_alive(enabled: bool) -> None:
    """Keep the Web UI server alive indefinitely after completion so the user can read the result and download reports."""
    if not enabled:
        return

    print("\n🌐 Optimization complete. Web UI remains active. Press Ctrl+C to exit.")
    while True:
        time.sleep(1)


def parse_args():
    parser = argparse.ArgumentParser(description="OPC Local Code Optimizer")
    parser.add_argument(
        "project_path",
        type=str,
        nargs="?",
        default=None,
        help="Absolute path to the target project directory (optional with --web-ui)",
    )
    parser.add_argument(
        "--goal",
        type=str,
        default="Improve code quality, performance, and architecture",
        help="The primary optimization goal",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=5,
        help="Maximum number of optimization rounds",
    )
    parser.add_argument(
        "--archive-every",
        type=int,
        default=3,
        help="Archive historical data every N rounds",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without actually modifying project files",
    )
    parser.add_argument(
        "--auto", action="store_true", help="Auto-continue without user interaction"
    )
    parser.add_argument(
        "--resume", action="store_true", help="Resume from last checkpoint"
    )
    # LLM configuration
    parser.add_argument(
        "--model", type=str, default=None, help="Default LLM model (e.g. openai/gpt-4o)"
    )
    parser.add_argument(
        "--plan-model", type=str, default=None, help="LLM model for plan node"
    )
    parser.add_argument(
        "--execute-model", type=str, default=None, help="LLM model for execute node"
    )
    parser.add_argument(
        "--test-model", type=str, default=None, help="LLM model for test/review node"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="LLM call timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--web-ui",
        action="store_true",
        help="Launch Minecraft-style 3D Web UI in browser",
    )
    parser.add_argument(
        "--http-port",
        type=int,
        default=DEFAULT_WEB_UI_HTTP_PORT,
        help="Preferred HTTP port for Web UI startup (WebSocket uses HTTP+1)",
    )
    parser.add_argument(
        "--formatter",
        type=str,
        default=None,
        help="Explicit formatter command (e.g. 'black', 'ruff format')",
    )
    parser.add_argument(
        "--no-format",
        action="store_true",
        help="Disable auto-formatting after code modifications",
    )

    args = parser.parse_args()

    # project_path is required unless --web-ui is used standalone
    if args.project_path and not os.path.exists(args.project_path):
        raise ValueError(f"Target project path does not exist: {args.project_path}")
    if not args.project_path and not args.web_ui:
        parser.error("project_path is required (or use --web-ui for standalone mode)")

    return args


def main():
    _configure_stdio()
    from ui.tui import OPCConsole

    tui = OPCConsole()
    tui.print_header()

    # Graceful shutdown handler
    def signal_handler(sig, frame):
        tui.print_error("Received interrupt signal. Shutting down gracefully...")
        LLMService.print_usage_summary()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        args = parse_args()

        # Initialize OpenTelemetry tracing (no-op if not installed)
        from utils.telemetry import init_tracing

        init_tracing()

        # ── Extract core execution to a helper function ──
        def _execute_session(run_args, web_already_started=False):
            if run_args.model:
                os.environ["DEFAULT_LLM_MODEL"] = run_args.model
            if run_args.timeout != 120:
                os.environ["LLM_TIMEOUT"] = str(run_args.timeout)

            if getattr(run_args, "no_format", False):
                os.environ["OPC_FORMATTER"] = "none"
            elif getattr(run_args, "formatter", None):
                os.environ["OPC_FORMATTER"] = run_args.formatter

            llm_config = {
                "model": run_args.model,
                "plan_model": run_args.plan_model,
                "execute_model": run_args.execute_model,
                "test_model": run_args.test_model,
                "timeout": run_args.timeout,
            }

            config = OptimizerConfig(
                project_path=run_args.project_path,
                optimization_goal=run_args.goal,
                max_rounds=run_args.max_rounds,
                archive_every_n_rounds=run_args.archive_every,
            )

            _setup_gitignore(config.project_path)

            print(f"📁 Target Project : {config.project_path}")
            print(f"🎯 Goal           : {config.optimization_goal}")
            print(f"🔄 Max Rounds     : {config.max_rounds}")
            print(f"📦 Archive Every  : {config.archive_every_n_rounds} rounds")
            if run_args.dry_run:
                print("🏜️  Dry Run        : YES (no file modifications)")
            if run_args.auto:
                print("🤖 Auto Mode      : YES (no user interaction)")

            for label, key in [
                ("Plan", "plan_model"),
                ("Execute", "execute_model"),
                ("Test", "test_model"),
            ]:
                model_val = llm_config.get(key)
                if model_val:
                    print(f"🧠 {label} Model   : {model_val}")

            from utils.config_loader import load_config

            load_config(
                cli_args={
                    "goal": config.optimization_goal,
                    "max_rounds": config.max_rounds,
                    "dry_run": run_args.dry_run,
                    "auto": run_args.auto,
                },
                project_path=config.project_path,
            )

            from graph import create_optimizer_graph

            app = create_optimizer_graph(project_path=config.project_path)

            if run_args.web_ui and not web_already_started:
                try:
                    from ui.web_server import start_server, _resolve_web_ui_ports

                    web_ui_http_port, web_ui_ws_port = _resolve_web_ui_ports(
                        run_args.http_port
                    )
                    start_server(
                        http_port=web_ui_http_port,
                        ws_port=web_ui_ws_port,
                        open_browser=True,
                    )
                    print(f"🌐 Web UI started: http://localhost:{web_ui_http_port}")
                except Exception as e:
                    print(f"⚠️  Web UI failed to start: {e}")

            initial_state = _prepare_initial_state(config, run_args, llm_config, tui)

            try:
                from ui.web_server import set_optimizer_state

                set_optimizer_state(initial_state)
            except Exception:
                pass

            print("\n🚀 Starting OPC Optimization Loop...")
            latest_state = _stream_graph_events(app, initial_state, tui)

            tui.print_final_report(
                total_rounds=latest_state.get("current_round", 1),
                reports=latest_state.get("round_reports", []),
            )
            LLMService.print_usage_summary()

        # ── Standalone Web UI mode ──
        if args.web_ui and not args.project_path:
            print("⛏️  OPC Optimizer — Web UI Mode")
            print("🌐 Starting Web UI server...")
            try:
                from ui.web_server import start_server, wait_for_config, _StaticHandler

                # Need to resolve ports manually before starting server in case defaults are used
                web_ui_http_port, web_ui_ws_port = _resolve_web_ui_ports(args.http_port)
                start_server(
                    http_port=web_ui_http_port,
                    ws_port=web_ui_ws_port,
                    open_browser=True,
                    landing=True,
                    fetch_news=True,
                )
                print(f"🌐 Web UI: http://localhost:{web_ui_http_port}")

                while True:
                    print(
                        "\n⏳ Waiting for configuration from browser (Landing Page)..."
                    )
                    web_config = wait_for_config()

                    import copy

                    run_args = copy.copy(args)
                    run_args.project_path = web_config.get("path", "")
                    run_args.goal = web_config.get("goal", args.goal)
                    run_args.max_rounds = web_config.get("max_rounds", args.max_rounds)
                    run_args.auto = False  # Web UI mode uses interactive review
                    run_args.skip_plan_review = bool(
                        web_config.get("skip_plan_review", False)
                    )
                    if web_config.get("model"):
                        run_args.model = web_config["model"]

                    if not run_args.project_path or not os.path.exists(
                        run_args.project_path
                    ):
                        print(f"❌ Invalid project path: {run_args.project_path}")
                        continue

                    print(f"✅ Config received: {run_args.project_path}")
                    _StaticHandler._landing_mode = False

                    # Run the optimization session
                    _execute_session(run_args, web_already_started=True)

                    print(
                        "\n🌐 Optimization complete. Waiting for new task on landing page..."
                    )
                    _StaticHandler._landing_mode = True

            except Exception as e:
                print(f"❌ Web UI failed: {e}")
                import traceback

                traceback.print_exc()
                return
        else:
            # ── CLI Mode or Single-Shot Web UI ──
            _execute_session(args, web_already_started=False)
            _keep_webui_alive(args.web_ui)

    except KeyboardInterrupt:
        tui.print_error("Interrupted by user.")
        LLMService.print_usage_summary()
    except Exception as e:
        tui.print_error(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
