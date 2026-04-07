import logging
import time
import traceback
from typing import Callable, Optional

from langgraph.graph import StateGraph, END

if __package__:
    from .state import OptimizerState
    from .nodes.plan import plan_node
    from .nodes.execute import execute_node
    from .nodes.test import test_node
    from .nodes.archive import archive_node
    from .nodes.report import report_node
    from .nodes.interact import interact_node
    from .nodes.task_router import task_router_node
else:
    from state import OptimizerState
    from nodes.plan import plan_node
    from nodes.execute import execute_node
    from nodes.test import test_node
    from nodes.archive import archive_node
    from nodes.report import report_node
    from nodes.interact import interact_node
    from nodes.task_router import task_router_node

logger = logging.getLogger("opc.graph")


def safe_node_wrapper(node_name: str, node_fn: Callable) -> Callable:
    """Wrap a node function with try-except, timing, tracing, and event emission."""

    def wrapper(state: OptimizerState) -> OptimizerState:
        try:
            from .utils.telemetry import trace_span
        except ImportError:
            from utils.telemetry import trace_span

        # Emit node_start event for Web UI
        try:
            try:
                from .ui.web_server import emit
            except ImportError:
                from ui.web_server import emit

            emit(
                "node_start",
                {"node": node_name, "round": state.get("current_round", 1)},
            )
            # Emit round_start when plan begins (first node of each round)
            if node_name == "plan":
                emit("round_start", {"round": state.get("current_round", 1)})
        except Exception as e:
            logger.debug(f"Failed to emit node_start: {e}")

        start = time.time()
        with trace_span(f"node.{node_name}", {"round": state.get("current_round", 1)}):
            try:
                # Set trace context so LLM calls are tagged (v2.6.0)
                try:
                    try:
                        from .utils.trace_logger import get_trace_logger
                    except ImportError:
                        from utils.trace_logger import get_trace_logger

                    get_trace_logger().set_context(
                        node_name, state.get("current_round", 1)
                    )
                except Exception as e:
                    logger.debug(f"Failed to set trace context: {e}")
                result = node_fn(state)
                elapsed = time.time() - start
                # Record timing
                timings = result.get("node_timings", {}) or {}
                timings[node_name] = round(elapsed, 2)
                result["node_timings"] = timings
                logger.info(f"Node '{node_name}' completed in {elapsed:.2f}s")
                # ── Round timeout guard (autoresearch-inspired) ──
                round_timeout = result.get("round_timeout", 0) or 0
                round_start = result.get("round_start_time", 0) or 0
                if round_timeout > 0 and round_start > 0:
                    round_elapsed = time.time() - round_start
                    if round_elapsed > round_timeout:
                        logger.error(
                            f"Round timeout: {round_elapsed:.0f}s > {round_timeout}s limit"
                        )
                        raise TimeoutError(
                            f"Round timeout exceeded: {round_elapsed:.0f}s > {round_timeout}s limit"
                        )
                # Emit node_complete event
                try:
                    try:
                        from .ui.web_server import emit
                    except ImportError:
                        from ui.web_server import emit

                    emit(
                        "node_complete",
                        {
                            "node": node_name,
                            "elapsed": round(elapsed, 2),
                            "round": result.get("current_round", 1),
                        },
                    )
                    # Emit diff_update after execute node
                    if node_name == "execute":
                        modified = result.get("modified_files", [])
                        project_path = result.get("project_path", "")
                        if modified and project_path:
                            import os, difflib

                            diff_files = []
                            for fpath in modified:
                                abs_path = os.path.join(project_path, fpath)
                                bak_path = abs_path + ".bak"
                                try:
                                    if os.path.exists(bak_path) and os.path.exists(
                                        abs_path
                                    ):
                                        with open(
                                            bak_path,
                                            "r",
                                            encoding="utf-8",
                                            errors="replace",
                                        ) as f:
                                            old_lines = f.readlines()
                                        with open(
                                            abs_path,
                                            "r",
                                            encoding="utf-8",
                                            errors="replace",
                                        ) as f:
                                            new_lines = f.readlines()
                                        diff = list(
                                            difflib.unified_diff(
                                                old_lines,
                                                new_lines,
                                                fromfile=f"a/{fpath}",
                                                tofile=f"b/{fpath}",
                                                lineterm="",
                                            )
                                        )
                                        if diff:
                                            diff_content = "\n".join(
                                                line.rstrip() for line in diff[:80]
                                            )  # cap at 80 lines
                                            diff_files.append(
                                                {
                                                    "filename": fpath,
                                                    "content": diff_content,
                                                }
                                            )
                                    else:
                                        # No .bak, just show a summary from code_diff
                                        diff_text = result.get("code_diff", "")
                                        for line in diff_text.split("\n"):
                                            if fpath in line:
                                                reason = (
                                                    line.split(":", 1)[1].strip()
                                                    if ":" in line
                                                    else "modified"
                                                )
                                                diff_files.append(
                                                    {
                                                        "filename": fpath,
                                                        "content": f"+{reason}",
                                                    }
                                                )
                                                break
                                except Exception as e:
                                    logger.warning(
                                        f"Diff computation failed for {fpath}: {e}"
                                    )
                                    diff_files.append(
                                        {"filename": fpath, "content": "+modified"}
                                    )
                            if diff_files:
                                emit("diff_update", {"files": diff_files})
                    # NOTE: round_end and optimization_complete are emitted by
                    # interact_node itself (not here) so that the timing is correct:
                    # interact decides when a round ends and whether to stop,
                    # only it knows the result of the WebSocket wait.
                except Exception as e:
                    logger.warning(f"Failed to emit node_complete/diff_update: {e}")
                return result
            except Exception as e:
                elapsed = time.time() - start
                logger.error(f"Node '{node_name}' failed after {elapsed:.2f}s: {e}")
                logger.debug(traceback.format_exc())
                errors = state.get("execution_errors", []) or []
                errors.append(f"[{node_name}] {type(e).__name__}: {e}")
                state["execution_errors"] = errors
                timings = state.get("node_timings", {}) or {}
                timings[node_name] = round(elapsed, 2)
                state["node_timings"] = timings
                # Emit node_error event
                try:
                    try:
                        from .ui.web_server import emit
                    except ImportError:
                        from ui.web_server import emit

                    emit(
                        "node_error",
                        {
                            "node": node_name,
                            "error": str(e),
                            "elapsed": round(elapsed, 2),
                        },
                    )
                except Exception as e:
                    logger.warning(f"Failed to emit node_error: {e}")
                return state

    wrapper.__name__ = node_name
    return wrapper


def should_continue(state: OptimizerState) -> str:
    """Conditional edge logic after interact_node."""
    if state.get("should_stop", False):
        return "end"
    return "continue"


def should_test(state: OptimizerState) -> str:
    """Conditional edge after execute_node: skip test for fast-path (low) tasks."""
    if state.get("fast_path", False):
        logger.info("fast_path=True: skipping test node, jumping to archive")
        return "skip_test"
    return "run_test"


def _build_skill_dispatcher(skill_name: str, legacy_fn: Callable) -> Callable:
    """Dispatch to skill bridge in skill_mode, otherwise keep legacy path."""

    def dispatcher(state: OptimizerState) -> OptimizerState:
        run_mode = state.get("run_mode", "legacy_mode")
        if run_mode != "skill_mode":
            state["skill_name"] = "legacy_pipeline"
            return legacy_fn(state)

        try:
            try:
                from .utils.skill_bridge import run_skill
            except ImportError:
                from utils.skill_bridge import run_skill
            return run_skill(skill_name, state)
        except Exception as exc:
            logger.warning(
                "Skill dispatch failed for '%s', fallback to legacy node: %s",
                skill_name,
                exc,
            )
            state["run_mode"] = "legacy_mode"
            state["failure_type"] = "skill_dispatch_failed"
            state["router_decision"] = (
                f"skill_dispatch:fallback_legacy({skill_name}:{type(exc).__name__})"
            )
            state["skill_name"] = "legacy_pipeline"
            return legacy_fn(state)

    dispatcher.__name__ = f"{skill_name}_dispatcher"
    return dispatcher


def create_optimizer_graph(project_path: str = None, skill_registry: Optional[object] = None):
    """Build and compile the LangGraph workflow."""

    # Initialize the graph with the state schema
    workflow = StateGraph(OptimizerState)

    # Load baseline skills from registry (Phase 1).
    try:
        from .utils.skill_registry import build_core_skill_registry
    except ImportError:
        from utils.skill_registry import build_core_skill_registry

    registry = skill_registry or build_core_skill_registry()
    required_core_skills = ("plan", "execute", "test", "report")
    for name in required_core_skills:
        spec = registry.get(name)
        if spec is None:
            raise ValueError(f"Missing required core skill registration: {name}")
        if not spec.enabled:
            raise ValueError(f"Required core skill is disabled: {name}")
    logger.info(
        "Core skills registered: %s",
        ", ".join(s.name for s in registry.list(enabled_only=False)),
    )

    # Add all nodes with error isolation
    workflow.add_node("task_router", safe_node_wrapper("task_router", task_router_node))
    workflow.add_node(
        "plan", safe_node_wrapper("plan", _build_skill_dispatcher("plan", plan_node))
    )
    workflow.add_node(
        "execute",
        safe_node_wrapper("execute", _build_skill_dispatcher("execute", execute_node)),
    )
    workflow.add_node(
        "test", safe_node_wrapper("test", _build_skill_dispatcher("test", test_node))
    )
    workflow.add_node("archive", safe_node_wrapper("archive", archive_node))
    workflow.add_node(
        "report",
        safe_node_wrapper("report", _build_skill_dispatcher("report", report_node)),
    )
    workflow.add_node(
        "interact", _build_skill_dispatcher("interact", interact_node)
    )  # No wrapper — interact must propagate stop signals

    # Define the strict linear flow
    workflow.set_entry_point("task_router")
    workflow.add_edge("task_router", "plan")

    # Build edge chain — default linear order (execute has conditional branch)
    node_order = ["plan", "execute", "test", "archive", "report", "interact"]

    # ── Plugin injection (v2.2.0) ───────────────────────────────
    if project_path:
        try:
            from .plugins import discover_plugins
        except ImportError:
            from plugins import discover_plugins

        plugins = discover_plugins(project_path)
        for plugin in plugins:
            workflow.add_node(plugin.name, safe_node_wrapper(plugin.name, plugin.run))
            # Insert plugin right after its insert_after node
            try:
                idx = node_order.index(plugin.insert_after)
                node_order.insert(idx + 1, plugin.name)
                logger.info(
                    f"Plugin '{plugin.name}' injected after '{plugin.insert_after}'"
                )
            except ValueError:
                node_order.append(plugin.name)
                logger.warning(
                    f"Plugin '{plugin.name}' insert_after='{plugin.insert_after}' "
                    f"not found; appending to end"
                )

    # ── Conditional routing ──────────────────────────────────────
    workflow.add_conditional_edges(
        "execute",
        should_test,
        {
            "run_test": "test",  # Normal path: run test
            "skip_test": "archive",  # Fast path: skip test
        },
    )

    # Linear chain through remaining nodes
    workflow.add_edge("test", "archive")
    workflow.add_edge("archive", "report")
    workflow.add_edge("report", "interact")

    # ── Loop back or end ──────────────────────────────────────────
    workflow.add_conditional_edges(
        "interact",
        should_continue,
        {
            "continue": node_order[1],  # Loop back to execute for next round
            "end": END,
        },
    )

    # Compile the graph
    return workflow.compile()
