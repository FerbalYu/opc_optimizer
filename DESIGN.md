# Design

## Project Summary
This delivery pass fixes the reliability gaps exposed by a real 5-round OPC
Optimizer trial. The priority is not broad feature work; it is making the
workflow trustworthy when it reports success, runs tests, protects user-owned
verification files, and advances through LangGraph rounds.

## Goals
- Ensure the compiled LangGraph executes the full round chain:
  `task_router -> plan -> execute -> test -> archive -> report -> interact`.
- Keep CLI completion stable by matching `main.py` calls to `OPCConsole` APIs.
- Prevent real pytest/assertion failures from being downgraded to environment
  errors and static validation.
- Make validation mode explicit so reports do not present static fallback as
  real test success.
- Protect tests and other read-only files when the user asks to fix
  implementation code while keeping tests unchanged.
- Add focused regression tests for the above behavior.

## Non-Goals
- Rewriting LangGraph orchestration or replacing the node model.
- Replacing the LLM planning/execution protocol.
- Building a new Web UI or introducing a frontend build toolchain.
- Solving all import debt, all reporting polish, or all autonomous workflow
  quality issues in one pass.
- Making live LLM output deterministic in CI.

## Users and Workflows
- Developer: runs `python -m opc_optimizer` from the package parent and expects
  the workflow to complete without crashing at summary time.
- Operator: runs autonomous rounds and needs test status to mean what it says.
- Maintainer: uses regression tests to catch graph topology, validation, and
  write-scope regressions before another live 5-round trial.

## Product Decisions
- Treat false success as higher severity than incomplete optimization. A failed
  real test should remain a failed real test unless the tooling itself truly
  cannot run.
- Treat acceptance-test files as read-only by default for "fix failing tests"
  goals unless the user explicitly asks to add or change tests.
- Prefer small, auditable fixes before broader refactors. The limited refactor
  scope is verification and write-scope control only.

## Technical Decisions
- `utils.static_validator.is_env_error()` should use specific tooling-error
  patterns instead of broad `ImportError` / `cannot find` matches.
- `nodes.test.test_node()` should populate structured validation metadata:
  `validation_mode`, `real_tests_ran`, and `static_fallback_reason`.
- Static fallback can pass static validation, but must not masquerade as a real
  test pass in state, metrics, or reports.
- `nodes.execute` should derive read-only paths from the goal and round
  contract, then reject modifications before writing files.
- Graph topology tests should inspect compiled edges directly.

## Limited Refactor Scope
- Introduce small helper functions before introducing new classes.
- If the verification code keeps growing, extract a narrow
  `utils/verification_runner.py` with a structured `VerificationResult`.
- If write-scope rules keep growing, extract a narrow `RoundScope` helper for
  writable and read-only paths.
- Keep reports as consumers of structured state; do not let report code infer
  validation truth from free-form terminal text.

## Architecture
`main.py` prepares state and streams the compiled graph from `graph.py`. The
graph nodes remain in `nodes/`. `execute_node` owns LLM patch parsing and file
writes. `test_node` owns build/test/UI verification and now records whether
validation was real or static. `report_node` persists round reports and metrics.

The trial failure showed two weak boundaries:

- Verification boundary: build/test output was interpreted with overly broad
  environment-error matching.
- Write-scope boundary: acceptance-test files could be modified even when the
  goal said they should remain unchanged.

This pass tightens those boundaries without changing the public CLI contract.

## Acceptance Criteria
- [x] `python -m opc_optimizer --help` works from the parent directory.
- [x] Compiled graph includes `plan -> execute` and does not include
  `plan -> END`.
- [x] `OPCConsole` exposes the methods used by `main.py` summary output.
- [x] Pytest assertion/runtime failures are not classified as environment
  errors.
- [x] Static fallback is represented as static fallback, not real test success.
- [x] Test files are blocked when the goal says tests should remain unchanged.
- [x] Focused regression tests pass.
- [x] Full test suite is run or any blocker is documented.

## Assumptions
- Existing dirty worktree changes are agent work from the current delivery and
  should be preserved unless proven unrelated.
- Live LLM runs are useful for manual validation but too variable for CI.
- Current project documents remain the source of truth for autonomous work.

## Risks
- Over-tightening environment-error detection may turn genuine missing-tool
  cases into normal failures. Mitigation: keep explicit tests for command-not-
  found and missing pytest/tooling cases.
- Read-only path detection from natural language may be imperfect. Mitigation:
  start with conservative rules for tests and explicit "tests unchanged" goals.
- Static fallback semantics may require updates across reports and tests.
  Mitigation: add structured fields first, then adapt consumers.

## Suggested Later Improvements
- Extract `VerificationRunner` and `RoundScope` once the current helpers settle.
- Add deterministic e2e coverage with mocked LLM responses.
- Continue gradual package-relative import migration.
- Improve final report wording for static fallback and low-value rounds.

## Visual Companion Direction
The next product direction is a CLI-first 3D visual companion. The CLI remains
the command surface for scriptable runs, while the existing Three.js monitor
acts as a live sidecar for understanding state, rounds, diffs, and final
outcome.

## Visual Companion Goals
- Add a `--visual` CLI mode that runs the normal optimizer and opens the 3D
  monitor as a companion window.
- Keep the companion read-mostly: it should display workflow events without
  taking over the CLI interaction loop.
- Reuse the existing WebSocket event stream and Three.js UI instead of
  introducing a separate desktop stack.
- Make the visual mode visibly distinct in Chinese as "CLI 副屏".

## Visual Companion Non-Goals
- Replacing `--web-ui` or the current browser-based control flow.
- Building a native desktop app in this pass.
- Redesigning the full 3D scene or adding complex character animation before
  the CLI/visual contract is stable.

## Visual Companion Acceptance Criteria
- [x] `python -m opc_optimizer <project> --visual` starts the 3D monitor and
  then runs the same optimizer flow as CLI mode.
- [x] `--visual` appears in package help output.
- [x] In visual companion mode, round-end events are emitted to the 3D monitor
  without waiting for Web UI commands.
- [x] The monitor shows a Chinese "CLI 副屏" mode indicator.
- [x] Focused tests cover the new CLI flag, visual-only interaction behavior,
  static UI marker, and Web UI readiness endpoint.

## Visual Insight Direction
The selected next ideas are: five-round value curve, file-change wall, prompt
microscope, round health score, and next-step suggestions. The first slice keeps
these as structured report events and a Chinese Web UI insight panel; later
iterations can map the same data into richer 3D objects.

## Visual Insight Acceptance Criteria
- [x] Each report round can build a structured `round_insight` payload.
- [x] The payload includes health score, value label, value curve point,
  file-wall classification, prompt-microscope checks, and next actions.
- [x] The 3D monitor exposes a Chinese "洞察" tab for these fields.
- [x] Focused and full regression tests cover the insight utility and static UI
  hooks.
