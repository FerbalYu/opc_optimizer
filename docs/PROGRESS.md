# Progress

Updated: 2026-06-02T00:00:00+08:00

## Current Plan
- [x] Add the Agent tool registry and runtime.
- [x] Route build/test/UI, Context7 docs, and post-write formatting through tool
  calls without changing existing result fields.
- [x] Expose skill-chain and Agent Loop observability in state, metrics, and Web
  UI events.
- [x] Let `skill_chain` drive the graph route in `skill_mode`, with
  `legacy_mode` retaining the old default chain.
- [x] Add Web UI Agent Loop and tool-call surfaces.
- [x] Run full verification after the Agent evolution pass.

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
- [x] Replaced the temporary browser app-mode `--desktop` idea with a PySide6
  desktop shell, QWebEngineView, QWebChannel bridge, and dedicated WebView UI.
- [x] Added a desktop Three.js dashboard that uses local static assets and no
  WebSocket transport.
- [x] Reworked the desktop Three.js dashboard back to the original
  Minecraft-style office worker concept: six workflow stations, desks, props,
  file bricks, insight beacon, and a block character that moves on node events.
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
- [x] Added `utils/tool_registry.py` with built-in tool metadata for build,
  test, UI, Context7 docs, and formatting.
- [x] Added `utils/tool_runtime.py` with normalized tool results,
  path-escape checks, `tool_calls` recording, and WebSocket tool events.
- [x] Migrated the normal `test_node` build/test/UI verification path through
  the tool runtime while preserving legacy fallback behavior.
- [x] Migrated execute-stage Context7 docs grounding and post-write formatting
  through the tool runtime.
- [x] Added skill-chain observability and made `skill_mode` skip the `test`
  node when the resolved chain excludes it.
- [x] Replaced fixed graph edges with conditional skill-chain routing so
  `skill_mode` can start from the first declared skill and continue through the
  declared chain; `archive` remains an automatic system node before report.
- [x] Added Agent Loop state, current sub-agent, fallback reason, and recent
  tool calls to the Web UI overview.
- [x] Switched the default LLM model from `openai/gpt-4o` to **MiniMax-M3**
  (`utils/llm.py`).
- [x] Added `MiniMax-M3` to `LLMService.MODEL_PRICING` (placeholder price
  `0.70/0.70` USD per 1M tokens, pending official M3 quote).
- [x] Updated UI/landing model selector, `opc.config.example.yaml`,
  `utils/config_template.py` template, and `README.md` quick-start to point
  at MiniMax-M3; legacy `minimax` pricing entry kept as prefix-fallback.

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
- `python -m pytest tests/test_tool_registry.py tests/test_tool_runtime.py tests/test_state_models.py tests/test_metrics_tracker.py tests/test_skill_contract.py tests/test_task_router.py tests/test_graph.py tests/test_ui_visual_state.py -q`: 52 passed.
- `python -m pytest tests/test_build_verification.py tests/test_nodes_integration.py tests/test_step21_22.py tests/test_self_repair.py tests/test_skill_chain_integration.py tests/test_skill_bridge.py tests/test_check_skill_docs_freshness.py tests/test_gen_skill_docs.py -q`: 66 passed.
- `python -m pytest --collect-only -q`: 575 collected after adding tool-layer tests.
- `python -m pytest -q`: 575 passed, 1 existing async mock resource warning.
- `python scripts/check_skill_docs_freshness.py`: passed.
- `git diff --check`: passed, with CRLF normalization warnings only.
- Browser check at `http://127.0.0.1:8799/index.html?mode=visual`: Agent Loop panel and tool-call list visible.
- `python -m pytest tests/test_context7.py tests/test_execute.py tests/test_tool_runtime.py -q`: 35 passed.
- `python -m pytest tests/test_nodes_integration.py tests/test_e2e_workflow.py -q`: 17 passed.
- `python -m pytest tests/test_graph.py tests/test_skill_router.py tests/test_task_router.py tests/test_skill_chain_integration.py -q`: 25 passed.
- `python -m pytest tests/test_state_models.py tests/test_metrics_tracker.py tests/test_tool_registry.py tests/test_tool_runtime.py -q`: 31 passed.
- `python -m pytest --collect-only -q`: 579 collected after adding
  skill-chain graph-routing coverage.
- `python -m pytest -q`: 579 passed, 1 existing async mock resource warning.
- `git diff --check`: passed, with CRLF normalization warnings only.
- `python -m pytest tests/test_step4_features.py -q`: 20 passed (added 3
  MiniMax-M3 tests: default-signature, pricing-table presence, cost
  calculation).
- `python -m pytest -q`: 582 passed, 1 existing async mock resource warning
  (3 new MiniMax-M3 tests included; collect-only count moved from 579 → 582).
- `python -m opc_optimizer --help`: works, all CLI flags preserved after the
  model default change.
- Smoke `LLMService.__init__`: default `model_name="MiniMax-M3"`, pricing
  entry `(0.70, 0.70)`.
- `python -m pytest tests/test_package_entrypoint.py tests/test_main_webui_ports.py -q`: 6 passed.
- `python -m pytest --collect-only -q`: 584 collected after adding desktop
  mode tests.
- `python -m opc_optimizer --help`: `--desktop` is listed and `project_path`
  says it is optional with `--web-ui/--desktop`.
- `git diff --check`: passed, with CRLF normalization warnings only.
- `python -m pytest tests/test_desktop_bridge.py tests/test_desktop_ui_static.py tests/test_desktop_app.py tests/test_desktop_packaging.py tests/test_main_webui_ports.py tests/test_package_entrypoint.py tests/test_web_server.py -q`: 34 passed.
- `python -m pytest tests/test_ui_visual_state.py tests/test_interact_webui.py -q`: 13 passed.
- `python -m py_compile ui/desktop/app.py ui/desktop/bridge.py desktop_entry.py scripts/build_desktop_portable.py`: passed.
- Desktop visual smoke at `http://127.0.0.1:8891/index.html`: no browser
  console errors; WebGL canvas present; control, insights, and reports regions
  present.
- Desktop visual smoke at `http://127.0.0.1:8765/index.html`: Playwright loaded
  the dedicated desktop page, verified no current console errors, captured the
  office-worker scene, and injected `node_start`, `round_insight`,
  `diff_update`, and tool-call events. The block character moved to the report
  station and the dashboard counters/logs updated.
- PySide6 host smoke with `QT_QPA_PLATFORM=offscreen`: `DesktopMainWindow`
  initialized and loaded `ui/desktop/web/index.html`.
- `python -m pytest --collect-only -q`: 595 collected after adding desktop
  bridge/UI/package tests.

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
- The collect-only count increased from 565 to 579 because this pass added
  focused tool-registry/runtime and skill-chain graph-routing coverage.

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
- Promote MiniMax-M3 to the project default LLM. `DEFAULT_LLM_MODEL` env
  override and per-node `--plan-model` / `--execute-model` / `--test-model`
  flags still take precedence, so users can pin MiniMax-M2.7 / OpenAI /
  Claude / DeepSeek without code changes.
