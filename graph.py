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

DEFAULT_SKILL_CHAIN = ["plan", "execute", "test", "report"]
SUPPORTED_SKILL_NODES = {"plan", "execute", "test", "report", "interact"}


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

            loop_step = {
                "plan": "think",
                "execute": "act",
                "test": "observe",
                "archive": "reflect",
                "report": "reflect",
                "interact": "reflect",
                "task_router": "think",
            }.get(node_name, "think")
            state["active_agent"] = node_name
            state["agent_loop_step"] = loop_step
            emit(
                "node_start",
                {"node": node_name, "round": state.get("current_round", 1)},
            )
            emit(
                "agent_step",
                {
                    "agent": node_name,
                    "step": loop_step,
                    "round": state.get("current_round", 1),
                    "skill_chain": state.get("skill_chain", []),
                    "fallback_reason": state.get("fallback_reason", ""),
                },
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
    if state.get("run_mode") == "skill_mode":
        skill_chain = state.get("skill_chain", []) or []
        if skill_chain and "test" not in skill_chain:
            logger.info("skill_chain excludes test: skipping test node")
            return "skip_test"
    if state.get("fast_path", False):
        logger.info("fast_path=True: skipping test node, jumping to archive")
        return "skip_test"
    return "run_test"


def _resolve_skill_chain(state: OptimizerState) -> list[str]:
    """Return the effective skill chain for this round.

    legacy_mode deliberately ignores any experimental skill_chain override so
    the old linear workflow remains stable.
    """
    if state.get("run_mode", "legacy_mode") != "skill_mode":
        return list(DEFAULT_SKILL_CHAIN)

    raw_chain = state.get("skill_chain", []) or DEFAULT_SKILL_CHAIN
    chain: list[str] = []
    for skill_name in raw_chain:
        if skill_name in SUPPORTED_SKILL_NODES and skill_name not in chain:
            chain.append(skill_name)
    return chain or list(DEFAULT_SKILL_CHAIN)


def _first_skill_node(state: OptimizerState) -> str:
    """Route from task_router or loop restart to the first declared skill."""
    return _resolve_skill_chain(state)[0]


def _next_declared_skill(state: OptimizerState, current: str) -> str:
    """Find the next requested skill after the current workflow node."""
    chain = _resolve_skill_chain(state)
    if current not in chain:
        return "interact"

    next_index = chain.index(current) + 1
    if next_index >= len(chain):
        return "interact"
    return chain[next_index]


def _route_after_plan(state: OptimizerState) -> str:
    """Route after plan according to the effective skill chain."""
    return _next_declared_skill(state, "plan")


def _route_after_execute(state: OptimizerState) -> str:
    """Route after execute, preserving fast-path and archive behavior."""
    if should_test(state) == "run_test":
        return "test"
    return "archive"


def _route_after_archive(state: OptimizerState) -> str:
    """Archive is a system node; continue to report only if requested."""
    if state.get("run_mode", "legacy_mode") != "skill_mode":
        return "report"
    chain = _resolve_skill_chain(state)
    return "report" if "report" in chain else "interact"


def _route_after_report(state: OptimizerState) -> str:
    """Report always hands control to interact for loop/stop decisions."""
    return "interact"


def _route_after_interact(state: OptimizerState) -> str:
    """Loop back to the first requested skill, or finish."""
    if should_continue(state) == "end":
        return "end"
    return _first_skill_node(state)


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
            state["fallback_reason"] = f"skill_dispatch_failed:{skill_name}:{type(exc).__name__}"
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

    workflow.set_entry_point("task_router")

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
        "task_router",
        _first_skill_node,
        {
            "plan": "plan",
            "execute": "execute",
            "test": "test",
            "report": "report",
            "interact": "interact",
        },
    )
    workflow.add_conditional_edges(
        "plan",
        _route_after_plan,
        {
            "execute": "execute",
            "test": "test",
            "report": "report",
            "interact": "interact",
        },
    )
    workflow.add_conditional_edges(
        "execute",
        _route_after_execute,
        {
            "test": "test",  # Normal path: run test
            "archive": "archive",  # Fast path / chain skip: archive before report
        },
    )

    # Linear chain through remaining nodes
    workflow.add_edge("test", "archive")
    workflow.add_conditional_edges(
        "archive",
        _route_after_archive,
        {
            "report": "report",
            "interact": "interact",
        },
    )
    workflow.add_conditional_edges(
        "report",
        _route_after_report,
        {
            "interact": "interact",
        },
    )

    # ── Loop back or end ──────────────────────────────────────────
    workflow.add_conditional_edges(
        "interact",
        _route_after_interact,
        {
            "plan": "plan",
            "execute": "execute",
            "test": "test",
            "report": "report",
            "interact": "interact",
            "end": END,
        },
    )

    # Compile the graph
    return workflow.compile()
