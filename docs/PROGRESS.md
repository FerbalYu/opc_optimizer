# Progress

Updated: 2026-05-20T10:10:00+08:00

## Current Plan
- [x] Preserve the previous 5-round reliability fixes and Chinese visible
  language pass.
- [x] Record the CLI-first 3D visual companion direction in `DESIGN.md`.
- [x] Add `--visual` as a CLI companion mode.
- [x] Keep visual companion mode from taking over CLI interaction.
- [x] Add focused regression coverage.
- [x] Run focused and full verification.
- [x] Add the selected visual insight slice: value curve, file wall, prompt
  microscope, health score, and next actions.
- [x] Add visual insight v2: map round insights into the Three.js scene.

## Completed
- [x] Ran an isolated sample project trial in
  `D:\workflow\opc\src\opc_optimizer_eval_20260518-214221`.
- [x] Confirmed the original sample baseline failed 6/6 tests.
- [x] Found that the compiled graph previously stopped at `plan -> END`.
- [x] Added the missing `plan -> execute` edge and looped `interact` back to
  `plan`.
- [x] Added TUI methods required by `main.py` summary output.
- [x] Added graph topology and TUI API regression tests.
- [x] Re-ran a live 5-round trial and confirmed the workflow now reaches 5/5
  rounds.
- [x] Confirmed live 5-round quality is still not trustworthy: real pytest
  status was downgraded to static fallback, and tests were modified despite the
  goal saying tests should remain unchanged.
- [x] Updated `DESIGN.md` for the validation reliability delivery pass.
- [x] Replaced broad environment-error matching with specific tooling-error
  patterns and tests.
- [x] Added structured validation metadata:
  `validation_mode`, `real_tests_ran`, and `static_fallback_reason`.
- [x] Updated round evaluation, reports, and metrics so static fallback is not
  treated as real test success.
- [x] Added read-only test-file filtering in execute scope resolution.
- [x] Added low-value/no-op auto-commit skipping in `report_node`.
- [x] Fixed package compatibility aliases so `plugins` resolves to the real
  package module, not an empty shell.
- [x] Fixed self-repair parsing to use `parse_llm_output()` and the parser's
  `filepath` / `old_content_snippet` / `new_content` shape.
- [x] Normalized simple LLM path wrappers such as `<stats_tool.py>` while still
  rejecting XML/tool placeholder paths.
- [x] Stripped invisible LLM formatting characters such as BOM before applying
  Python patches.
- [x] Normalized `pytest` commands to run through the current interpreter with
  `python -m pytest`.
- [x] Treated legacy "No build command configured" output as skipped success
  instead of a failed build.
- [x] Preserved partial implementation changes when real pytest fails, so later
  rounds can build on useful progress; rollback remains for technical build
  failures.
- [x] Added `--visual` CLI mode for a Three.js 3D companion window.
- [x] Added a Web UI `/health` readiness endpoint used by CLI startup.
- [x] Added "CLI 副屏" visual mode labeling in the Web UI.
- [x] Added visual companion interaction behavior so WebSocket clients receive
  round-end events without taking over the CLI prompt.
- [x] Added `utils.visual_insights.build_round_insight()` for structured visual
  companion insight events.
- [x] Added a Web UI "洞察" tab with five-round value curve, file wall, prompt
  microscope, health score, and next-action chips.
- [x] Added a 3D insight layer with health beacon, five-round value bars, and
  file-change bricks.

## In Progress
- None.

## Blockers
- None.

## Verification
- `python -m pytest tests/test_graph.py tests/test_tui.py tests/test_package_entrypoint.py -q`: 14 passed.
- `python -m pytest tests/test_static_validator.py tests/test_build_verification.py tests/test_execute.py tests/test_step21_22.py tests/test_metrics_tracker.py tests/test_step6_features.py tests/test_graph.py tests/test_tui.py tests/test_package_entrypoint.py -q`: 99 passed.
- `python -m pytest -q`: 549 passed.
- Live trial after graph/TUI fixes: completed 5/5 rounds, but true original
  acceptance was only 4/6 and test files were modified.
- Live trial after validation/write-scope fixes in
  `D:\workflow\opc\src\opc_optimizer_eval_regression_20260518-221821`:
  completed 5/5 rounds with real LLM calls loaded from `.env`; `python -m
  pytest -q` ended at 7/8 passed, `tests/test_stats_tool.py` had no diff, and
  no `static fallback` / env-error downgrade appeared in the run log.
- `python -m pytest tests/test_build_verification.py tests/test_nodes_integration.py tests/test_self_repair.py tests/test_step8_diff_parser.py tests/test_execute.py -q`: 98 passed.
- `python -m pytest -q`: 556 passed, 1 warning from an existing async mock
  resource warning.
- Final live 5-round trial in
  `D:\workflow\opc\src\opc_optimizer_eval_regression_20260518-233634`:
  baseline `python -m pytest -q` was 5/8 passed; OPC completed 5/5 rounds;
  final original pytest was 8/8 passed; `tests/test_stats_tool.py` had no diff.
  Final report:
  `C:\Users\ecgoi\.opc\.opc_workspace\2a811eb2\reports\final_report.md`.
- `python -m pytest tests/test_interact_webui.py tests/test_package_entrypoint.py tests/test_ui_visual_state.py tests/test_web_server.py tests/test_main_webui_ports.py -q`: 34 passed.
- `python -m pytest -q`: 562 passed.
- `git diff --check`: passed, with CRLF normalization warnings only.
- `python -m pytest tests/test_visual_insights.py tests/test_ui_visual_state.py tests/test_step6_features.py tests/test_prompt_language.py -q`: 25 passed.
- `python -m pytest -q`: 565 passed.
- `git diff --check`: passed, with CRLF normalization warnings only.

## Review Notes
- `utils.static_validator.is_env_error()` is now intentionally narrower; missing
  tool cases remain covered by tests.
- `nodes.test.test_node()` now records explicit validation mode and does not
  mark static fallback as real test pass.
- `nodes.execute.execute_node()` now treats tests as read-only for
  implementation-fix goals unless test changes are explicitly requested.
- The live trial generated target-project artifacts and commits in the isolated
  sample project only; the OPC repo itself has not been committed.
- The final live trial reached the target acceptance criteria, but the sample
  target's own auto-commits included `.opclog`, `.bak`, and `__pycache__`
  artifacts; cleanup of target-project commit scope remains a follow-up.
- The CLI still prints "Stop reason: User requested stop" when max rounds are
  reached; final reports correctly say "Reached max rounds".

## Suggestions
- Add deterministic mocked e2e coverage around the specific 5-round sample
  scenario.
- Restrict target-project auto-commits to meaningful source changes, excluding
  `.opclog`, `__pycache__`, and `.bak` artifacts.
- Align CLI stop-reason summary with final report wording when max rounds are
  reached.
- Extend the 3D scene after the CLI contract is stable: round orbit, file-change
  wall, and final before/after settlement screen.

## Decisions Since DESIGN.md
- Use a limited refactor: helper functions and structured fields first; no
  LangGraph rewrite.
