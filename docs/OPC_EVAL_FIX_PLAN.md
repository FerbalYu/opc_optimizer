# OPC 5 轮实测问题修正计划

更新时间：2026-05-18

## 背景

本次使用隔离样例项目 `D:\workflow\opc\src\opc_optimizer_eval_20260518-214221` 对 OPC 执行真实 5 轮自动优化验证。

样例项目基线状态：

- 原始测试：`python -m pytest -q`
- 基线结果：6 个测试全部失败
- 目标约束：修复 `stats_tool.py`，保持公开函数名和测试文件不变

第一次运行 OPC 时，暴露出主流程无法完整执行：

- 编译后的 LangGraph 只有 `task_router -> plan -> END`
- CLI 汇总阶段调用了不存在的 `OPCConsole.print_section`

在补齐最小流程修复后，OPC 可以完整跑完 5 轮，但真实优化结果仍不可靠。

## 实测结论

5 轮后，用原始验收口径复测：

- 原始基线：0/6 通过
- OPC 5 轮后：4/6 通过

仍失败的问题：

- `parse_ints("1, nope, 3")` 没有按原始测试要求抛出 `ValueError`
- `summarize("")` 仍会因为 `median([])` 触发 `IndexError`

更严重的问题：

- OPC 修改了 `tests/test_stats_tool.py`，把验收标准改成适配当前实现
- 真实 `pytest` 失败被误判为环境错误，并降级成 `static_python` 通过
- 报告中的 `build_passed=true` / `test_passed=true` 与真实测试结果不一致
- 后续轮次识别出低价值和目标偏移，但没有有效恢复到正确实现路径

## 复测结论

完成本计划修正后，重新创建隔离样例项目
`D:\workflow\opc\src\opc_optimizer_eval_regression_20260518-233634` 执行真实 5
轮回归。

复测结果：

- 样例基线：`python -m pytest -q` 为 5/8 通过。
- OPC 执行：完成 5/5 轮，使用真实 LLM 调用。
- 最终验收：`python -m pytest -q` 为 8/8 通过。
- 测试保护：`git diff -- tests/test_stats_tool.py` 无输出，测试文件未被修改。
- 最终报告：
  `C:\Users\ecgoi\.opc\.opc_workspace\2a811eb2\reports\final_report.md`。

复测过程中继续修正的新增问题：

- 自修复导入了不存在的 `parse_search_replace_blocks`，已改为使用
  `parse_llm_output()` 并适配统一字段结构。
- LLM 会输出 `<stats_tool.py>` 这类简单尖括号文件名，解析器现可接受真实文件名并继续拒绝 XML/占位符。
- LLM patch 中的 BOM / 零宽字符会导致 Python `compile()` 误报语法错误，应用前已清理。
- 独立 `pytest` 可执行文件与手工 `python -m pytest` 的导入口径不一致，已统一为当前解释器执行。
- “No build command configured — skipped.” 旧格式输出曾被误判为构建失败，已按跳过成功处理。
- 真实 pytest 失败但已有部分修复时不应回滚，现只对技术构建失败自动回滚。

## 修正目标

本轮修正的目标不是提升模型能力，而是提升 OPC 工作流的可信度：

1. 真实测试失败不能被误判为环境错误。
2. 用户明确要求不变的测试文件必须受到保护。
3. 报告中的通过状态必须来自真实验证或明确标注为静态降级。
4. 低价值轮次不能继续提交污染目标项目。
5. 图拓扑、CLI 汇总和 5 轮执行链路必须有回归测试覆盖。

## 修改计划

### 有限重构范围

本计划需要重构，但不做“大重构”：

- 不重写 LangGraph。
- 不重写整个 optimizer。
- 不替换现有 LLM plan/execute/test/report 协议。
- 先修 P0 行为缺陷，再在验证与写入边界内做小范围抽取。

允许的重构范围：

- 将验证结果逐步结构化为 `validation_mode`、`real_tests_ran`、`static_fallback_reason` 等字段。
- 如 `nodes/test.py` 继续膨胀，可抽取窄接口 `utils/verification_runner.py`。
- 如只读/可写范围规则继续膨胀，可抽取 `RoundScope` 辅助对象。
- 报告层只消费结构化结果，不再从自由文本里猜测真实测试状态。

### 1. 固化主流程链路修复

现状：

- 已发现 `plan -> execute` 缺边会导致流程在计划阶段结束。
- 已发现 `interact` 继续时应回到下一轮 `plan`，而不是跳过规划直接进入 `execute`。

计划：

- 保留 `graph.py` 的完整链路：
  `task_router -> plan -> execute -> test -> archive -> report -> interact`
- `execute` 继续保留 `run_test` / `skip_test` 条件分支。
- `interact` 的 `continue` 分支回到 `plan`。
- 在 `tests/test_graph.py` 中固定拓扑断言，禁止再次出现 `plan -> END`。

验收：

```bash
python -m pytest tests/test_graph.py -q
```

### 2. 修正 CLI 汇总接口缺失

现状：

- `main.py` 调用 `tui.print_section()` 和 `tui.print_info()`。
- `ui/tui.py` 当前缺少对应方法时会导致优化完成后崩溃。

计划：

- 在 `OPCConsole` 中补齐 `print_section()`。
- 在 `OPCConsole` 中补齐 `print_info()`。
- 增加 TUI 回归测试。

验收：

```bash
python -m pytest tests/test_tui.py tests/test_package_entrypoint.py -q
```

### 3. 收紧环境错误识别

现状：

- `utils/static_validator.py::is_env_error()` 使用宽泛字符串匹配。
- `ImportError`、`cannot find` 等模式可能把真实测试失败误判为环境问题。
- 一旦误判，`nodes/test.py` 会降级到静态验证，并把 `build_passed/test_passed` 标为通过。

计划：

- 将环境错误识别从宽泛 substring 改为更具体的规则。
- 只把以下情况视为环境错误：
  - 命令不存在：`command not found`、Windows `is not recognized as an internal`
  - 可执行文件缺失：`No such file or directory` 且指向命令启动失败
  - 包管理或工具链缺失：`No module named pytest`、`npm ERR! missing script`
- 不再把普通 `ImportError`、`ModuleNotFoundError`、`cannot find` 一律视为环境错误。
- 对 `pytest` 已经成功启动并返回断言失败、异常栈、测试失败摘要的输出，必须保持失败。

新增测试：

- pytest 断言失败不是环境错误。
- `IndexError` / `ValueError` / `AssertionError` 不是环境错误。
- `No module named pytest` 是环境错误。
- 命令不存在是环境错误。

验收：

```bash
python -m pytest tests/test_build_verification.py tests/test_static_validator.py -q
```

### 4. 区分真实验证与静态降级

现状：

- 静态降级后 `build_passed` 和 `test_passed` 可能都显示为 true。
- 最终报告很容易让用户误以为真实测试通过。

计划：

- 在 `build_result` 中明确加入：
  - `validation_mode`: `real` / `static_fallback`
  - `real_tests_ran`: `true` / `false`
  - `static_fallback_reason`
- 当进入 `static_fallback` 时：
  - `test_passed` 不应表示真实测试通过
  - 报告标题和指标必须显示“静态降级，未运行真实测试”
- `round_evaluation.objective_completed` 不能仅凭静态验证设为 true，除非目标明确是文档/静态类改动。

验收：

```bash
python -m pytest tests/test_nodes_integration.py tests/test_metrics_tracker.py -q
```

### 5. 保护测试文件和只读目标

现状：

- 本次目标明确要求“测试文件不变”，但 OPC 修改了 `tests/test_stats_tool.py`。
- 后续报告虽然识别出 out-of-scope，但改动已经进入目标项目和自动提交。

计划：

- 从用户目标和 round contract 中提取只读约束。
- 默认策略：
  - 当目标是“修测试失败”时，测试文件默认为只读，除非目标明确要求“补测试/改测试”。
  - 当 acceptance checks 引用测试文件时，不代表测试文件可写。
- 在 `execute_node` 应用修改前拦截只读路径。
- 如果 LLM 输出包含只读文件修改：
  - 不写入文件
  - 标记本轮 `readonly_violation`
  - 触发 replan 或自修正
- 自动提交时不应提交只读违规轮次。

新增测试：

- 目标包含“测试文件不变”时，`tests/` 修改会被拒绝。
- acceptance check 中出现测试路径，不会自动加入 writable target。
- 只读违规不会被标记为 objective completed。

验收：

```bash
python -m pytest tests/test_execute.py tests/test_step21_22.py -q
```

### 6. 改进低价值轮次处理

现状：

- 第 4/5 轮已经识别 `No changes parsed from LLM output` 和 out-of-scope，但流程仍继续到最大轮数。
- 低价值轮次仍可能留下日志、checkpoint、自动提交和目标污染。

计划：

- 对低价值轮次增加硬处理：
  - 无有效代码修改时，不提交目标项目。
  - out-of-scope 修改时，自动回滚本轮改动。
  - 连续低价值达到阈值时停止并输出失败原因，而不是继续消耗轮次。
- 交互层 `interact_node` 保留继续能力，但自动模式下应优先避免重复无效轮次。

验收：

```bash
python -m pytest tests/test_interact_webui.py tests/test_self_repair.py tests/test_run_mode_rollout.py -q
```

### 7. 加一个真实 5 轮端到端回归样例

现状：

- 单元测试覆盖很多组件，但没有固定“建小项目 -> 跑 OPC -> 比较真实 pytest”的验收。

计划：

- 增加一个轻量 e2e 脚本或测试夹具：
  - 生成临时 Python 项目。
  - 初始化 git。
  - 注入确定性 Mock LLM 响应，避免真实 API 波动。
  - 跑 2 到 3 轮流程，验证完整节点链路。
  - 真实运行 `python -m pytest -q`。
  - 确认测试文件未被修改。
- 真实 LLM 的 5 轮验证保留为手动评估脚本，不作为 CI 必跑项。

验收：

```bash
python -m pytest tests/test_e2e_workflow.py tests/test_graph.py -q
```

## 优先级

P0：

- 图链路完整性
- TUI 缺失方法
- 环境错误误判
- 静态降级报告语义

P1：

- 测试文件只读保护
- 低价值轮次回滚/停止策略

P2：

- 固化端到端评估脚本
- 优化报告可读性和指标一致性

## 完成标准

本计划完成后，应满足：

- `python -m opc_optimizer --help` 从包父目录正常运行。
- 编译后的 LangGraph 不再出现 `plan -> END`。
- CLI 模式完整执行后不因 TUI 方法缺失崩溃。
- pytest 断言失败不会被降级成环境错误。
- 静态降级不会伪装成真实测试通过。
- 用户要求测试文件不变时，OPC 不会写入 `tests/`。
- 隔离样例项目的原始验收口径达到 6/6 通过，且测试文件无 diff。

## 建议验证命令

```bash
python -m pytest tests/test_graph.py tests/test_tui.py tests/test_package_entrypoint.py -q
python -m pytest tests/test_build_verification.py tests/test_execute.py tests/test_nodes_integration.py -q
python -m pytest -q
```

手动回归：

```bash
python -m opc_optimizer D:\workflow\opc\src\opc_optimizer_eval_20260518-214221 --goal "修复 stats_tool.py 的测试失败并提高边界情况处理，保持现有公开函数名和测试文件不变" --auto --skip-plan-review --max-rounds 5 --run-mode legacy_mode
python -m pytest -q
git diff -- tests
```
