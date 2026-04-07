import os
import sys
import argparse
import signal
import logging
import socket
import time
import hashlib

if __package__:
    from .state import OptimizerConfig
    from .utils.llm import LLMService
    from .utils.constants import DEFAULT_WEB_UI_HTTP_PORT, MAX_PORT_SCAN_ATTEMPTS
else:
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
    config: "OptimizerConfig", run_args, llm_config: dict, tui, run_mode: str
) -> dict:
    """Prepare initial state for optimizer graph execution."""
    initial_state = None
    if getattr(run_args, "resume", False):
        try:
            from .utils.checkpoint import load_checkpoint

            initial_state = load_checkpoint(config.project_path)
            if initial_state:
                print(
                    f"🔄 Resumed from checkpoint: Round {initial_state.get('current_round', '?')}"
                )
                initial_state["auto_mode"] = run_args.auto
                initial_state["dry_run"] = run_args.dry_run
                initial_state["should_stop"] = False
                initial_state["llm_config"] = llm_config
                initial_state["run_mode"] = run_mode
                initial_state.setdefault(
                    "skill_name",
                    "skill_pipeline" if run_mode == "skill_mode" else "legacy_pipeline",
                )
                initial_state.setdefault("router_decision", "legacy_resume")
                initial_state.setdefault("failure_type", "none")
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
            "run_mode": run_mode,
            "skill_name": (
                "skill_pipeline" if run_mode == "skill_mode" else "legacy_pipeline"
            ),
            "router_decision": "legacy_linear",
            "failure_type": "none",
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
                from .ui.web_server import set_optimizer_state

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
    parser.add_argument(
        "--skip-plan-review",
        action="store_true",
        help="Skip plan review step (use with --auto)",
    )
    parser.add_argument(
        "--run-mode",
        type=str,
        choices=["legacy_mode", "skill_mode"],
        default=None,
        help="Execution mode marker for observability (defaults to OPC_RUN_MODE or legacy_mode)",
    )
    parser.add_argument(
        "--skill-gray-percent",
        type=int,
        default=None,
        help="Skill mode rollout percentage (0-100, defaults to OPC_SKILL_GRAY_PERCENT)",
    )

    args = parser.parse_args()

    # project_path is required unless --web-ui is used standalone
    if args.project_path and not os.path.exists(args.project_path):
        raise ValueError(f"Target project path does not exist: {args.project_path}")
    if not args.project_path and not args.web_ui:
        parser.error("project_path is required (or use --web-ui for standalone mode)")

    return args


def _resolve_run_mode(run_args) -> str:
    """Resolve execution mode with explicit override and gray rollout fallback."""
    mode = getattr(run_args, "run_mode", None) or os.getenv("OPC_RUN_MODE", "")
    if not mode:
        gray_percent = getattr(run_args, "skill_gray_percent", None)
        if gray_percent is None:
            raw_percent = os.getenv("OPC_SKILL_GRAY_PERCENT", "").strip()
            if raw_percent:
                try:
                    gray_percent = int(raw_percent)
                except ValueError:
                    logging.warning(
                        "Invalid OPC_SKILL_GRAY_PERCENT '%s', fallback to 0",
                        raw_percent,
                    )
                    gray_percent = 0
            else:
                gray_percent = 0

        if gray_percent < 0:
            gray_percent = 0
        if gray_percent > 100:
            gray_percent = 100

        if gray_percent <= 0:
            return "legacy_mode"
        if gray_percent >= 100:
            return "skill_mode"

        project = getattr(run_args, "project_path", "") or ""
        goal = getattr(run_args, "goal", "") or ""
        seed = f"{project}|{goal}"
        bucket = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % 100
        return "skill_mode" if bucket < gray_percent else "legacy_mode"

    mode = mode.strip()
    if mode not in ("legacy_mode", "skill_mode"):
        logging.warning(
            "Invalid run mode '%s', fallback to 'legacy_mode' (allowed: legacy_mode/skill_mode)",
            mode,
        )
        return "legacy_mode"
    return mode


def main():
    _configure_stdio()
    from .ui.tui import OPCConsole

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
        from .utils.telemetry import init_tracing

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
            run_mode = _resolve_run_mode(run_args)

            _setup_gitignore(config.project_path)

            print(f"📁 Target Project : {config.project_path}")
            print(f"🎯 Goal           : {config.optimization_goal}")
            print(f"🔄 Max Rounds     : {config.max_rounds}")
            print(f"📦 Archive Every  : {config.archive_every_n_rounds} rounds")
            print(f"🧭 Run Mode       : {run_mode}")
            if run_args.dry_run:
                print("🏜️  Dry Run        : YES (no file modifications)")
            if run_args.auto:
                print("🤖 Auto Mode      : YES (no user interaction)")

            for label, key in [
                ("Plan", "plan_model"),
                ("Execute", "execute_model"),
                ("Test", "test_model"),
            ]:
                val = llm_config.get(key)
                if val:
                    print(f"🔧 {label} Model    : {val}")

            if run_args.timeout != 120:
                print(f"⏱️  LLM Timeout    : {run_args.timeout}s")

            # Print formatter info
            formatter = os.environ.get("OPC_FORMATTER", "auto-detect")
            print(f"🎨 Formatter      : {formatter}")
            if getattr(run_args, "no_format", False):
                print("   (auto-formatting disabled)")

            # ── Build or load graph ──
            if web_already_started:
                print("\n⏳ Waiting for graph result via Web UI...")
                from .ui.web_server import wait_for_result

                result = wait_for_result()
                tui.print_success("Graph execution completed via Web UI!")
            else:
                from .graph import create_optimizer_graph

                app = create_optimizer_graph(config.project_path)
                initial_state = _prepare_initial_state(
                    config, run_args, llm_config, tui, run_mode
                )
                tui.print_phase("Starting optimization workflow", "🚀")
                result = _stream_graph_events(app, initial_state, tui)
                tui.print_success("Optimization workflow completed!")

            # ── Summary ──
            rounds = result.get("current_round", 0)
            errors = result.get("execution_errors", [])
            modified = result.get("modified_files", [])
            stops = result.get("should_stop", False)
            stop_reason = result.get("stop_reason", "")

            tui.print_section("Optimization Summary")
            print(f"   Rounds completed : {rounds}/{result.get('max_rounds', '?')}")
            print(f"   Files modified    : {len(modified)}")
            if errors:
                print(f"   Errors            : {len(errors)}")
                for err in errors[:5]:
                    print(f"      - {err[:80]}")
                if len(errors) > 5:
                    print(f"      ... and {len(errors)-5} more")
            else:
                print(f"   Errors            : 0")

            if stops:
                print(f"\n   Stop reason       : {stop_reason or 'User requested stop'}")

            # Print reports
            reports = result.get("round_reports", [])
            if reports:
                print(f"\n📋 Optimization Reports ({len(reports)}):")
                for i, r in enumerate(reports[:3], 1):
                    title = r.get("title", "Untitled") if isinstance(r, dict) else str(r)[:60]
                    print(f"   {i}. {title}")
                if len(reports) > 3:
                    print(f"   ... and {len(reports)-3} more")

            return result

        # ── Main execution dispatch ──
        if args.web_ui:
            http_port, ws_port = _resolve_web_ui_ports(args.http_port)
            print(f"🌐 Starting Web UI on http://127.0.0.1:{http_port}")
            print(f"   WebSocket: ws://127.0.0.1:{ws_port}")
            print()
            # Start web server in background thread
            from .ui.web_server import start_server
            import threading

            server_thread = threading.Thread(
                target=start_server,
                args=(http_port, ws_port),
                daemon=True,
            )
            server_thread.start()
            # Wait for server to be ready
            import urllib.request

            for _ in range(30):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{http_port}/health", timeout=1)
                    break
                except Exception:
                    time.sleep(0.5)
            else:
                tui.print_error("Web UI server failed to start")
                sys.exit(1)

            # Open browser
            import webbrowser

            webbrowser.open(f"http://127.0.0.1:{http_port}")

            if args.project_path:
                # Run graph with live UI updates
                result = _execute_session(args, web_already_started=False)
                _keep_webui_alive(True)
            else:
                # Standalone mode - just serve UI
                tui.print_success("Web UI ready! Configure project in browser.")
                tui.print_info("Press Ctrl+C to exit")
                while True:
                    time.sleep(1)
        else:
            # CLI mode
            result = _execute_session(args)
            if result.get("should_stop"):
                tui.print_info("Optimization stopped by user.")
            else:
                tui.print_success("All optimization rounds completed!")
            _keep_webui_alive(args.web_ui)

    except KeyboardInterrupt:
        tui.print_error("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logging.exception("Fatal error in main")
        tui.print_error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
