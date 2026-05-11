# OPC Optimizer

## Quick Start
- Install: `pip install -r requirements.txt`
- Test: `python -m pytest`
- Run CLI: from the parent of this directory, `python -m opc_optimizer --help`
- Run Web UI: from the parent of this directory, `python -m opc_optimizer --web-ui`

## Project Goal
OPC Optimizer is a local code optimization workflow that plans, edits, verifies, reports, and asks for user direction across multiple rounds.

## Architecture Overview
The workflow is orchestrated with LangGraph in `graph.py`. Nodes in `nodes/` implement planning, execution, testing, archiving, reporting, interaction, and task routing. `utils/` contains LLM, file, diff, formatter, security, workspace, trace, and project profile helpers. `ui/web_server.py` serves the static Web UI in `ui/web/` and streams runtime events over WebSocket.

See [DESIGN.md](DESIGN.md) for product and technical design.

## Directory Map
- `main.py`: CLI and Web UI startup orchestration.
- `graph.py`: LangGraph workflow construction and node wrapping.
- `nodes/`: workflow node implementations.
- `utils/`: shared services and safety utilities.
- `ui/`: terminal UI and Web UI server/static pages.
- `tests/`: automated regression tests.
- `docs/`: autonomous workflow state and delivery notes.

## Key Conventions
- Preserve package-mode execution: `python -m opc_optimizer` from the parent directory must keep working.
- Keep edits scoped to risk reduction, workflow correctness, and observable UI improvements.
- Do not remove user work from the dirty worktree.
- Prefer tests that exercise real entrypoints over tests that only pass because `sys.path` was modified.
- Keep Web UI changes build-free unless a frontend toolchain is explicitly introduced.

## Autonomous Workflow
Follow [docs/WORKFLOW.md](docs/WORKFLOW.md). Track current state in [docs/PROGRESS.md](docs/PROGRESS.md).

## Common Commands
- Install: `pip install -r requirements.txt`
- Collect tests: `python -m pytest --collect-only -q`
- Focused tests: `python -m pytest tests/test_package_entrypoint.py tests/test_ui_visual_state.py`
- Full tests: `python -m pytest`
