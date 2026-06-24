"""QWebChannel bridge for the OPC Desktop UI."""

from __future__ import annotations

import json
import os
import threading
from types import SimpleNamespace
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QFileDialog


class _DesktopConsole:
    """Small console shim used by the shared optimizer helpers."""

    def print_phase(self, phase_name: str, emoji: str = "") -> None:
        print(f"{emoji} {phase_name}".strip())

    def print_success(self, message: str) -> None:
        print(message)

    def print_info(self, message: str) -> None:
        print(message)

    def print_error(self, message: str) -> None:
        print(message)


def _json_response(ok: bool, **payload: Any) -> str:
    data = {"ok": ok}
    data.update(payload)
    return json.dumps(data, ensure_ascii=False)


def _build_run_args(config: dict[str, Any], initial_args: Any) -> SimpleNamespace:
    return SimpleNamespace(
        project_path=config.get("project_path") or getattr(initial_args, "project_path", None),
        goal=config.get("goal") or getattr(initial_args, "goal", ""),
        max_rounds=int(config.get("max_rounds") or getattr(initial_args, "max_rounds", 5)),
        archive_every=int(
            config.get("archive_every") or getattr(initial_args, "archive_every", 3)
        ),
        dry_run=bool(config.get("dry_run", getattr(initial_args, "dry_run", False))),
        auto=bool(config.get("auto", getattr(initial_args, "auto", False))),
        resume=bool(config.get("resume", getattr(initial_args, "resume", False))),
        model=config.get("model", getattr(initial_args, "model", None)),
        plan_model=config.get("plan_model", getattr(initial_args, "plan_model", None)),
        execute_model=config.get(
            "execute_model", getattr(initial_args, "execute_model", None)
        ),
        test_model=config.get("test_model", getattr(initial_args, "test_model", None)),
        timeout=int(config.get("timeout") or getattr(initial_args, "timeout", 120)),
        formatter=config.get("formatter", getattr(initial_args, "formatter", None)),
        no_format=bool(config.get("no_format", getattr(initial_args, "no_format", False))),
        skip_plan_review=bool(
            config.get("skip_plan_review", getattr(initial_args, "skip_plan_review", False))
        ),
        run_mode=config.get("run_mode", getattr(initial_args, "run_mode", None)),
        skill_gray_percent=config.get(
            "skill_gray_percent", getattr(initial_args, "skill_gray_percent", None)
        ),
    )


class DesktopBridge(QObject):
    """Bridge exposed to JavaScript through QWebChannel."""

    eventReceived = Signal(str)
    runStateChanged = Signal(str)

    def __init__(
        self,
        initial_args: Any,
        runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._initial_args = initial_args
        self._runner = runner
        self._thread: threading.Thread | None = None
        self._last_result: dict[str, Any] = {}

    @Slot(result=str)
    def initialConfig(self) -> str:
        return _json_response(
            True,
            project_path=getattr(self._initial_args, "project_path", "") or "",
            goal=getattr(self._initial_args, "goal", "") or "",
            max_rounds=getattr(self._initial_args, "max_rounds", 5),
            auto=getattr(self._initial_args, "auto", False),
            dry_run=getattr(self._initial_args, "dry_run", False),
        )

    @Slot(result=str)
    def chooseProject(self) -> str:
        folder = QFileDialog.getExistingDirectory(None, "选择目标项目目录")
        if not folder:
            return _json_response(False, error="cancelled")
        return _json_response(True, project_path=folder)

    @Slot(str, result=str)
    def startRun(self, config_json: str) -> str:
        if self._thread and self._thread.is_alive():
            return _json_response(False, error="optimizer_already_running")

        try:
            config = json.loads(config_json or "{}")
        except json.JSONDecodeError as exc:
            return _json_response(False, error=f"invalid_json:{exc}")

        project_path = config.get("project_path") or getattr(
            self._initial_args, "project_path", None
        )
        if not project_path or not os.path.isdir(project_path):
            return _json_response(False, error="project_path_not_found")
        config["project_path"] = project_path

        self._thread = threading.Thread(
            target=self._run_optimizer, args=(config,), daemon=True, name="opc-desktop-run"
        )
        self._thread.start()
        self.runStateChanged.emit(_json_response(True, state="running"))
        return _json_response(True, state="started")

    @Slot(str, result=str)
    def sendCommand(self, command_json: str) -> str:
        try:
            command = json.loads(command_json or "{}")
        except json.JSONDecodeError as exc:
            return _json_response(False, error=f"invalid_json:{exc}")

        if "action" not in command:
            return _json_response(False, error="missing_action")

        from ..web_server import submit_user_command

        submit_user_command(command)
        self.forwardEvent("command_received", {"action": command.get("action")})
        return _json_response(True, command=command)

    @Slot(result=str)
    def stopRun(self) -> str:
        return self.sendCommand(json.dumps({"action": "stop"}, ensure_ascii=False))

    @Slot(result=str)
    def lastResult(self) -> str:
        return _json_response(True, result=self._last_result)

    def forwardEvent(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        self.eventReceived.emit(
            json.dumps({"type": event_type, "data": data or {}}, ensure_ascii=False)
        )

    def _run_optimizer(self, config: dict[str, Any]) -> None:
        if self._runner is not None:
            try:
                self._last_result = self._runner(config)
                self.forwardEvent("optimization_complete", self._last_result)
                self.runStateChanged.emit(_json_response(True, state="complete"))
            except Exception as exc:
                self.forwardEvent("desktop_error", {"error": str(exc)})
                self.runStateChanged.emit(_json_response(False, state="error", error=str(exc)))
            return

        from ...graph import create_optimizer_graph
        from ...main import (
            _prepare_initial_state,
            _resolve_run_mode,
            _setup_gitignore,
            _stream_graph_events,
        )
        from ...state import OptimizerConfig
        from ..web_server import add_event_sink, remove_event_sink

        run_args = _build_run_args(config, self._initial_args)
        if run_args.model:
            os.environ["DEFAULT_LLM_MODEL"] = run_args.model
        if run_args.timeout != 120:
            os.environ["LLM_TIMEOUT"] = str(run_args.timeout)
        if run_args.no_format:
            os.environ["OPC_FORMATTER"] = "none"
        elif run_args.formatter:
            os.environ["OPC_FORMATTER"] = run_args.formatter

        llm_config = {
            "model": run_args.model,
            "plan_model": run_args.plan_model,
            "execute_model": run_args.execute_model,
            "test_model": run_args.test_model,
            "timeout": run_args.timeout,
        }
        optimizer_config = OptimizerConfig(
            project_path=run_args.project_path,
            optimization_goal=run_args.goal,
            max_rounds=run_args.max_rounds,
            archive_every_n_rounds=run_args.archive_every,
        )
        tui = _DesktopConsole()

        add_event_sink(self.forwardEvent)
        try:
            _setup_gitignore(optimizer_config.project_path)
            run_mode = _resolve_run_mode(run_args)
            app = create_optimizer_graph(optimizer_config.project_path)
            initial_state = _prepare_initial_state(
                optimizer_config, run_args, llm_config, tui, run_mode
            )
            result = _stream_graph_events(app, initial_state, tui)
            self._last_result = dict(result)
            self.forwardEvent("optimization_complete", self._last_result)
            self.runStateChanged.emit(_json_response(True, state="complete"))
        except Exception as exc:
            self.forwardEvent("desktop_error", {"error": str(exc)})
            self.runStateChanged.emit(_json_response(False, state="error", error=str(exc)))
        finally:
            remove_event_sink(self.forwardEvent)

