# Design

## Project Summary
This delivery pass strengthens OPC Optimizer by fixing high-risk execution/import issues and improving the Web UI's ability to show workflow state at a glance.

## Goals
- Make package-mode imports and `python -m opc_optimizer` entrypoints reliable.
- Add regression tests that catch package import regressions.
- Improve Web UI visualization for node state, progress, risk, timing, and recent activity.
- Keep the existing static Three.js Web UI architecture.

## Non-Goals
- Rewriting the workflow engine.
- Replacing the static Web UI with a bundler or framework.
- Cleaning all existing broad exception handling or all import style debt in one pass.
- Changing the LLM workflow contract.

## Users and Workflows
- Developer: runs the optimizer from the parent directory with `python -m opc_optimizer`, starts Web UI, and expects imports to work outside the test harness.
- Operator: watches Web UI during optimization and needs quick visual feedback on current node, completed nodes, errors, changed files, and timing.

## Product Decisions
- Treat package-mode import failure as the first blocker because it invalidates README usage and release packaging.
- Improve the existing Web UI rather than replacing it, because it already has Three.js, logs, diffs, rounds, stats, trace, and config tabs.
- Use lightweight dashboard elements and scene indicators instead of adding a build step.

## Technical Decisions
- Add a package initializer to provide compatibility aliases for the current absolute-import modules while preserving script-mode imports.
- Add focused tests for package imports and UI visualization markup/scripts.
- Add a Web UI overview rail and node state legend driven by existing WebSocket events.
- Keep all new frontend code in `ui/web/index.html`.

## Architecture
Package startup flows through `__main__.py` to `main.py`. `graph.py` imports package-relative nodes, while many node and utility modules still use legacy absolute imports. The package initializer bridges those names in package mode.

The Web UI receives WebSocket events from `ui/web_server.py`: `connected`, `node_start`, `node_complete`, `node_error`, `round_start`, `round_end`, `diff_update`, `round_history_update`, `cost_update`, `awaiting_input`, and `optimization_complete`. The enhanced visualization derives UI state from these events without changing backend event contracts.

## Acceptance Criteria
- [ ] From the parent directory, `import opc_optimizer.graph` succeeds.
- [ ] From the parent directory, `python -m opc_optimizer --help` exits successfully.
- [ ] Tests cover package entrypoint/import behavior.
- [ ] Web UI displays a compact workflow overview with node state, risk/errors, progress, changed files, and recent activity.
- [ ] Web UI visualization updates on `node_start`, `node_complete`, `node_error`, `round_start`, `round_end`, and `diff_update`.
- [ ] Focused tests pass.

## Assumptions
- Existing dirty worktree changes are intentional and must be preserved.
- Static HTML/CSS/JS tests are sufficient for this pass; full browser rendering is optional unless a UI regression requires it.
- The current root directory is intended to be importable as `opc_optimizer` from its parent.

## Risks
- Compatibility aliases can hide remaining import debt. Mitigation: add tests and document a future gradual migration to relative imports.
- Web UI script is large and single-file. Mitigation: keep additions localized and use stable element IDs for tests.
- CDN-based Three.js and Chart.js remain external dependencies. Mitigation: avoid adding new external frontend dependencies.

## Suggested Later Improvements
- Convert internal imports to package-relative imports module by module.
- Add a packaging file such as `pyproject.toml`.
- Split `ui/web/index.html` into separate static CSS and JS files.
- Add Playwright smoke coverage for the Web UI scene once network/CDN behavior is controlled.
