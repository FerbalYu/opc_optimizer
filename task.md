# OPC Optimizer 改造任务执行手册（给其他 LLM 直接用）

## 1. 文档目的

本文件用于统一 `opc_optimizer` 的改造执行流程，确保不同 LLM/工程师接手时：

- 理解一致。
- 执行顺序一致。
- 产物格式一致。
- 验收标准一致。

配套方案文档：`gstack_改造方案与实施计划.md`  
本手册是“执行协议”，不是“设计讨论”。

## 2. 任务总目标

- 将 `opc_optimizer` 逐步改造为“技能化工作流底座”，并保持现有能力稳定。
- 必须遵守“小步快跑 + 可回滚 + 可验证”原则。

## 3. 使用方式（每次开工先做）

每次任务开始时，先输出以下四项：

```md
【Task Start】
阶段: Phase X
子任务: <一句话描述>
影响文件: <文件列表>
验证方式: <测试命令/手工验证项>
```

如果任一项无法明确，先补齐上下文，禁止直接改代码。

同时必须创建“任务勾选卡”：

```md
【Task Checklist】

- [ ] ANALYZE 完成
- [ ] PLAN 完成
- [ ] IMPLEMENT 完成
- [ ] VERIFY 完成
- [ ] REPORT 完成
- [ ] HANDOFF 完成
```

规则：

- 未完成用 `[ ]`，完成后改为 `[x]`。
- 禁止跳过中间步骤直接勾选后续步骤。
- `VERIFY` 未通过时，`REPORT` 和 `HANDOFF` 只能标记为 `[ ]`。

## 4. 执行状态机（强制）

每个任务必须按以下状态推进，不可跳步：

1. `ANALYZE`：阅读相关文件，确认依赖与边界。
2. `PLAN`：给出精确改动点和验证命令。
3. `IMPLEMENT`：仅改本任务所需文件。
4. `VERIFY`：运行测试/诊断并记录结果。
5. `REPORT`：输出变更摘要、风险、下一步。
6. `HANDOFF`：更新本文件任务区状态，便于下一个 LLM 接续。

状态机勾选映射（必须同步更新）：

- `ANALYZE` 完成后：`- [x] ANALYZE 完成`
- `PLAN` 完成后：`- [x] PLAN 完成`
- `IMPLEMENT` 完成后：`- [x] IMPLEMENT 完成`
- `VERIFY` 通过后：`- [x] VERIFY 完成`
- `REPORT` 输出后：`- [x] REPORT 完成`
- `HANDOFF` 写入后：`- [x] HANDOFF 完成`

## 5. 开发约束（强制）

- 先读后写：修改前必须读目标文件完整上下文。
- 最小侵入：不顺手重构无关代码。
- 单任务提交：一次只做一个子目标。
- 可回滚：若验证失败，优先修复；必要时回退本任务改动。
- 禁止静默失败：命令失败必须记录原因和下一步动作。

## 6. 任务拆分规则（适用于本项目）

每个子任务只允许属于以下三类之一：

- `INFRA`：底座能力（registry/router/runtime/config）。
- `BRIDGE`：把现有节点技能化封装，保持行为等价。
- `QUALITY`：测试、文档生成、CI 校验与守护。

单个子任务推荐规模：

- 修改文件数 `<= 5`。
- 新增测试 `1~3` 个。
- 执行耗时 `<= 90` 分钟。

超出即拆分。

## 7. 标准产物清单（每个子任务都要有）

- 代码变更：最小必要实现。
- 测试变更：覆盖新增或改变行为。
- 文档变更：若行为/接口变化，更新对应文档。
- 任务记录：更新本文件任务区状态。
- 勾选记录：更新 `Task Checklist` 的 `[ ]/[x]` 状态。

## 8. 验证协议

优先级从高到低：

1. 目标相关测试（新增/修改）。
2. 受影响模块测试。
3. 项目核心回归测试（至少一组）。
4. 诊断检查（lint/type/diagnostics）。

建议命令（按项目实际可用性调整）：

```powershell
python -m pytest -q
python -m pytest tests/test_graph.py -q
python -m pytest tests/test_nodes_integration.py -q
```

若命令不可用，必须在报告中写明“不可用原因 + 替代验证”。

## 9. 失败与回滚协议

出现以下任一情况，必须触发回滚/止损流程：

- 新增错误且无法在当前任务窗口修复。
- 改动超出任务边界。
- 行为与预期不一致且定位不明。

处理步骤：

1. 停止新增改动。
2. 记录失败现象与影响范围。
3. 回退当前任务改动或降级到 `legacy_mode` 路径。
4. 输出阻塞信息，等待下一步决策。

## 10. 交接模板（必须使用）

```md
【Task Handoff】
阶段: Phase X
子任务: <名称>
状态: done | blocked | partial
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动: <文件列表>
      测试结果: <命令 + 通过/失败>
      风险与注意: <最多3条>
      下一步建议: <明确到文件/函数>
```

## 11. Phase 任务看板（持续更新）

### Phase 0 基线与观测

- [x] P0-1 基线数据采集（测试通过率、关键耗时、样本输入输出）
- [x] P0-2 新增运行模式标识（`legacy_mode`/`skill_mode`）
- [x] P0-3 新增观测字段（skill_name/router_decision/failure_type）

### Phase 1 技能注册中心

- [x] P1-1 新增 `utils/skill_registry.py` 与 `SkillSpec`
- [x] P1-2 接入 `plan/execute/test/report` 基础技能注册
- [x] P1-3 新增注册中心单测（冲突、禁用、查询）

### Phase 2 路由与前置协议

- [x] P2-1 新增 `utils/skill_router.py`
- [x] P2-2 统一 preamble 注入（session/round/profile/config）
- [x] P2-3 路由失败自动降级到 `legacy_mode`

### Phase 3 节点技能化桥接

- [x] P3-1 为 `plan/execute/test/interact/report` 建包装层
- [x] P3-2 统一技能输入输出契约
- [x] P3-3 跑通 `skill_mode` 最小闭环并对照 `legacy_mode`

### Phase 4 文档模板化

- [x] P4-1 建立 `skills/*.md.tmpl` 或扩展 `opcskills` 模板能力
- [x] P4-2 实现 `scripts/gen_skill_docs.py`
- [x] P4-3 增加文档新鲜度检查命令并接入 CI

### Phase 5 质量门禁

- [x] P5-1 技能级单元测试补齐
- [x] P5-2 技能链路集成测试补齐
- [x] P5-3 `legacy_mode` 回归对照测试补齐

### Phase 6 灰度启用

- [x] P6-1 灰度开关接入（CLI + 环境变量）
- [x] P6-2 运行数据观察与评估
- [x] P6-3 默认模式切换决策与回退预案

## 11.1 子任务执行看板模板（复制即用）

```md
### <子任务编号> <子任务名称>

- 状态: [ ] 未开始 [ ] 进行中 [ ] 已完成 [ ] 阻塞
- 类型: [ ] INFRA [ ] BRIDGE [ ] QUALITY
- 影响文件:
  - [ ] <file_a>
  - [ ] <file_b>
- 执行清单:
  - [ ] ANALYZE（已阅读目标文件）
  - [ ] PLAN（已给出改动点与验证命令）
  - [ ] IMPLEMENT（已完成最小改动）
  - [ ] VERIFY（验证通过）
  - [ ] REPORT（已输出总结）
  - [ ] HANDOFF（已更新交接信息）
- 验证记录:
  - [ ] 命令1: <cmd> -> <pass/fail>
  - [ ] 命令2: <cmd> -> <pass/fail>
- 结论:
  - [ ] 可合并
  - [ ] 需继续
  - [ ] 已阻塞（需人工决策）
```

## 11.2 Phase 0 示例（可直接开工）

> 示例目标：给其他 LLM 一个“第一步就能执行”的样板，避免只看模板不会落地。

```md
### P0-1 基线数据采集（测试通过率、关键耗时、样本输入输出）

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] INFRA [ ] BRIDGE [ ] QUALITY
- 影响文件:
  - [x] `task.md`
  - [x] `tests/`（仅读取，不改）
  - [x] `main.py`（仅读取，不改）
  - [x] `baseline_report.md`（新增）

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（读取测试结构、入口流程、现有日志字段）
  - [x] PLAN（明确采集口径与输出文件）
  - [x] IMPLEMENT（执行基线采集并新增 `baseline_report.md`）
  - [x] VERIFY（运行 3 条验证命令并记录结果）
  - [x] REPORT（输出基线结论、风险与建议）
  - [x] HANDOFF（更新 Phase 看板 + 交接）

- 基线采集口径:
  - [x] 测试通过率：总数、通过数、失败数
  - [x] 关键耗时：完整测试耗时、核心链路耗时
  - [x] 样本输入输出：至少 2 组（普通任务/复杂任务）

- 验证记录:
  - [x] 命令1: `python -m pytest -q` -> fail（4 errors in 0.44s）
  - [x] 命令2: `python -m pytest tests/test_graph.py -q` -> fail（ImportError in 0.13s）
  - [x] 命令3: `python -m pytest tests/test_nodes_integration.py -q` -> fail（11 failed in 0.81s）

- 产物要求:
  - [x] 产出 `baseline_report.md`（项目根目录）
  - [x] 报告中包含测试统计、耗时、样本 I/O、风险备注

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）
```

完成该示例任务后，请同步勾选：

- [x] `Phase 0 / P0-1` 主看板项
- [x] 对应 `Task Checklist` 六项状态
- [x] `Task Handoff` 输出

```md
【Task Handoff】
阶段: Phase 0
子任务: P0-1 基线数据采集
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- baseline_report.md（新增）
- task.md（P0-1 看板与示例状态更新）
  测试结果:
- python -m pytest -q -> fail（4 errors in 0.44s）
- python -m pytest tests/test_graph.py -q -> fail（ImportError in 0.13s）
- python -m pytest tests/test_nodes_integration.py -q -> fail（11 failed in 0.81s）
  风险与注意:
- 当前环境缺失关键依赖（langgraph、litellm）
- 包命名/导入路径存在 opc_optimizer 与 local_optimizer 混用
- 项目根目录识别依赖 pyproject.toml，当前路径下无法自动发现
  下一步建议:
- 先执行 P0-2：为 legacy_mode/skill_mode 增加统一模式标识与输出
```

### P0-2 新增运行模式标识（`legacy_mode`/`skill_mode`）

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] INFRA [ ] BRIDGE [ ] QUALITY
- 影响文件:
  - [x] `main.py`
  - [x] `state.py`
  - [x] `tests/test_state_models.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（阅读入口、状态定义、任务路由与方案文档）
  - [x] PLAN（确定模式标识只做观测，不改业务路径）
  - [x] IMPLEMENT（新增 `run_mode` 字段与 CLI/环境变量注入）
  - [x] VERIFY（运行目标测试并检查诊断）
  - [x] REPORT（记录本次变更与边界）
  - [x] HANDOFF（更新 Phase 看板与本节交接）

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_state_models.py -q` -> pass（9 passed）
  - [x] 命令2: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 0
子任务: P0-2 新增运行模式标识
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- main.py（新增 `--run-mode` 参数、`OPC_RUN_MODE` 兜底解析、启动输出、状态注入）
- state.py（新增 `run_mode` 字段与合法值校验）
- tests/test_state_models.py（补充默认值与非法值回退测试）
- task.md（更新 P0-2 看板与执行记录）
  测试结果:
- python -m pytest tests/test_state_models.py -q -> pass（9 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前仅新增“模式标识”，尚未引入 `skill_mode` 实际路由执行能力
- 下游节点尚未消费 `run_mode` 字段（符合 Phase 0 最小侵入目标）
- 需在 P0-3 统一补齐 `skill_name/router_decision/failure_type` 观测字段
  下一步建议:
- 执行 P0-3：优先在 `nodes/task_router.py` 与 `utils/metrics_tracker.py` 增加 `router_decision/failure_type` 观测输出

### P0-3 新增观测字段（skill_name/router_decision/failure_type）

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] INFRA [ ] BRIDGE [ ] QUALITY
- 影响文件:
  - [x] `state.py`
  - [x] `main.py`
  - [x] `nodes/task_router.py`
  - [x] `utils/metrics_tracker.py`
  - [x] `tests/test_metrics_tracker.py`
  - [x] `tests/test_state_models.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（确认观测字段落点在 state/task_router/metrics 链路）
  - [x] PLAN（保持最小侵入，只扩展状态与观测输出，不改业务流程）
  - [x] IMPLEMENT（补齐字段默认值、路由决策写入、失败类型归因）
  - [x] VERIFY（运行目标测试并检查诊断）
  - [x] REPORT（记录新增字段与归因规则）
  - [x] HANDOFF（更新主看板与交接块）

- 观测口径:
  - [x] `skill_name`：`legacy_pipeline` / `skill_pipeline`（由 `run_mode` 派生）
  - [x] `router_decision`：记录 `task_router` 的复杂度与 fast_path 决策
  - [x] `failure_type`：`node_error > build_failed > test_failed > low_value > none`

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_metrics_tracker.py -q` -> pass（12 passed）
  - [x] 命令2: `python -m pytest tests/test_state_models.py -q` -> pass（9 passed）
  - [x] 命令3: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 0
子任务: P0-3 新增观测字段
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- state.py（新增 `skill_name/router_decision/failure_type` 状态字段）
- main.py（初始化与 resume 路径注入观测字段默认值）
- nodes/task_router.py（写入 `router_decision` 与 `skill_name`）
- utils/metrics_tracker.py（输出三项观测字段与 `failure_type` 归因）
- tests/test_metrics_tracker.py（新增观测字段与失败归因断言）
- tests/test_state_models.py（新增状态默认值断言）
- task.md（更新 P0-3 看板与执行记录）
  测试结果:
- python -m pytest tests/test_metrics_tracker.py -q -> pass（12 passed）
- python -m pytest tests/test_state_models.py -q -> pass（9 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前 `skill_name` 仍为模式级标签，尚未细化到具体技能实例
- `failure_type` 为本地规则归因，后续可与真实异常分类枚举对齐
- 需在后续阶段统一沉淀到 Web UI 可视化展示字段
  下一步建议:
- 进入 Phase 1 / P1-1：新增 `utils/skill_registry.py` 与 `SkillSpec`

### P1-1 新增 `utils/skill_registry.py` 与 `SkillSpec`

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] INFRA [ ] BRIDGE [ ] QUALITY
- 影响文件:
  - [x] `utils/skill_registry.py`
  - [x] `tests/test_skill_registry.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（读取现有 skill_loader 与测试风格，确认底座边界）
  - [x] PLAN（先定义技能元数据契约，再提供注册中心基础 API）
  - [x] IMPLEMENT（新增 `SkillSpec` 与 `SkillRegistry`，支持注册/查询/启停）
  - [x] VERIFY（新增并运行针对性单测，检查诊断）
  - [x] REPORT（记录本次底座能力与边界）
  - [x] HANDOFF（更新主看板与交接信息）

- 交付能力:
  - [x] `SkillSpec`：`name/description/entrypoint/inputs/outputs/safety_level/enabled/resources`
  - [x] `SkillRegistry`：`register/register_many/get/has/list/disable/enable`
  - [x] 冲突保护：重复注册默认抛错，可通过 `replace_existing=True` 覆盖

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_skill_registry.py -q` -> pass（5 passed）
  - [x] 命令2: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 1
子任务: P1-1 新增 skill registry
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- utils/skill_registry.py（新增 `SkillSpec` 与 `SkillRegistry` 基础实现）
- tests/test_skill_registry.py（新增注册中心单测，覆盖定义校验/注册查询/启停/冲突）
- task.md（更新 P1-1 看板与执行记录）
  测试结果:
- python -m pytest tests/test_skill_registry.py -q -> pass（5 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前注册中心仅内存实现，未接入持久化或插件发现流程
- `entrypoint` 目前为字符串契约，尚未做动态导入校验
- `P1-2` 需把 `plan/execute/test/report` 技能注册真正接入运行路径
  下一步建议:
- 执行 P1-2：在图构建或启动初始化中注入基础技能注册流程

### P1-2 接入 `plan/execute/test/report` 基础技能注册

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] INFRA [ ] BRIDGE [ ] QUALITY
- 影响文件:
  - [x] `utils/skill_registry.py`
  - [x] `graph.py`
  - [x] `tests/test_skill_registry.py`
  - [x] `tests/test_graph.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（确认 graph 是基础技能注册的最小接入点）
  - [x] PLAN（新增核心技能构建函数并在 graph 构建时强制消费）
  - [x] IMPLEMENT（接入 `plan/execute/test/report`，缺失或禁用时显式报错）
  - [x] VERIFY（补充并运行注册中心与图构建测试）
  - [x] REPORT（记录接入方式与边界）
  - [x] HANDOFF（更新看板与交接）

- 接入细节:
  - [x] 新增 `build_core_skill_registry()`，内置注册 `plan/execute/test/report`
  - [x] `create_optimizer_graph()` 新增 `skill_registry` 入参，默认使用核心注册表
  - [x] 图构建前校验核心技能必须存在且启用，否则抛出 `ValueError`

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_skill_registry.py -q` -> pass（6 passed）
  - [x] 命令2: `python -m pytest tests/test_graph.py -q` -> pass（7 passed）
  - [x] 命令3: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 1
子任务: P1-2 基础技能注册接入
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- utils/skill_registry.py（新增 `build_core_skill_registry`，注册 plan/execute/test/report）
- graph.py（构建图时接入并校验核心技能注册）
- tests/test_skill_registry.py（新增核心注册表测试）
- tests/test_graph.py（新增核心技能缺失时报错测试）
- task.md（更新 P1-2 看板与执行记录）
  测试结果:
- python -m pytest tests/test_skill_registry.py -q -> pass（6 passed）
- python -m pytest tests/test_graph.py -q -> pass（7 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前注册信息仍以内存结构存在，尚未接入配置化启停
- `entrypoint` 仅作为契约字符串，动态导入校验待后续增强
- `interact/archive/task_router` 仍在传统节点注册路径，未纳入技能注册中心
  下一步建议:
- 执行 P1-3：补齐注册中心测试矩阵（冲突、禁用、查询边界与批量注册）

### P1-3 新增注册中心单测（冲突、禁用、查询）

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] QUALITY [ ] INFRA [ ] BRIDGE
- 影响文件:
  - [x] `tests/test_skill_registry.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（盘点现有测试覆盖，定位冲突/禁用/查询边界缺口）
  - [x] PLAN（仅新增测试，不改生产逻辑）
  - [x] IMPLEMENT（补齐 `register_many` 冲突、替换注册、缺失项查询与启停）
  - [x] VERIFY（运行目标测试并检查诊断）
  - [x] REPORT（记录覆盖范围扩展）
  - [x] HANDOFF（更新主看板与交接）

- 新增测试点:
  - [x] `register_many` 遇重复技能时抛错
  - [x] `replace_existing=True` 可覆盖旧技能定义
  - [x] 缺失技能的 `get/has/disable/enable` 返回符合预期

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_skill_registry.py -q` -> pass（9 passed）
  - [x] 命令2: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 1
子任务: P1-3 注册中心单测补齐
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- tests/test_skill_registry.py（新增冲突、禁用、查询边界测试）
- task.md（更新 P1-3 看板与执行记录）
  测试结果:
- python -m pytest tests/test_skill_registry.py -q -> pass（9 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前测试仍聚焦内存注册行为，未覆盖并发访问场景
- `entrypoint` 动态可执行性仍未校验（仅验证字符串契约）
- 后续接入 `skill_router` 后需补充跨模块集成测试
  下一步建议:
- 进入 Phase 2 / P2-1：新增 `utils/skill_router.py`

### P2-1 新增 `utils/skill_router.py`

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] INFRA [ ] BRIDGE [ ] QUALITY
- 影响文件:
  - [x] `utils/skill_router.py`
  - [x] `tests/test_skill_router.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（确认项目内尚无 skill_router，梳理 Phase 2 路由目标）
  - [x] PLAN（先实现纯函数路由器，稳定输出技能计划与降级信息）
  - [x] IMPLEMENT（新增 `SkillRoutePlan` 与 `route_skills` 路由策略）
  - [x] VERIFY（新增并运行路由器测试）
  - [x] REPORT（记录当前路由规则与边界）
  - [x] HANDOFF（更新主看板与交接信息）

- 路由能力:
  - [x] `legacy_mode` 透传为线性链路（plan/execute/test/report）
  - [x] `skill_mode` 默认链路输出 + `router_decision`
  - [x] 文档类低风险目标支持跳过 test 的 fast path
  - [x] 存在失败类型时强制保留 test（failure guard）

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_skill_router.py -q` -> pass（4 passed）
  - [x] 命令2: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 2
子任务: P2-1 skill_router 底座实现
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- utils/skill_router.py（新增 `SkillRoutePlan` 与 `route_skills`）
- tests/test_skill_router.py（新增 legacy/default/doc-only/failure-guard 路由测试）
- task.md（更新 P2-1 看板与执行记录）
  测试结果:
- python -m pytest tests/test_skill_router.py -q -> pass（4 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前为纯函数路由器，尚未接入主图执行路径
- 路由规则为 Phase 2 基线，后续需结合 preamble 与运行态扩展
- `fallback_reason` 已预留，但降级触发仍由后续集成层实现
  下一步建议:
- 执行 P2-2：统一 preamble 注入（session/round/profile/config）

### P2-2 统一 preamble 注入（session/round/profile/config）

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] INFRA [ ] BRIDGE [ ] QUALITY
- 影响文件:
  - [x] `utils/skill_preamble.py`
  - [x] `nodes/plan.py`
  - [x] `nodes/execute.py`
  - [x] `nodes/test.py`
  - [x] `state.py`
  - [x] `tests/test_skill_preamble.py`
  - [x] `tests/test_state_models.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（梳理 session/round/profile/config 的现有来源与传递链路）
  - [x] PLAN（新增统一 preamble 工具，按最小侵入接入 plan/execute/test）
  - [x] IMPLEMENT（注入 preamble 到状态与提示词，补充状态字段）
  - [x] VERIFY（新增 preamble 单测并回归 state 模型测试）
  - [x] REPORT（记录注入范围与边界）
  - [x] HANDOFF（更新主看板与交接信息）

- 注入能力:
  - [x] 统一生成 `session_id/round_id/project_profile/config` 上下文
  - [x] 统一渲染 `skill_preamble` 文本并写回 state
  - [x] 在 `plan/execute/test` 主提示词统一注入 preamble

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_skill_preamble.py -q` -> pass（2 passed）
  - [x] 命令2: `python -m pytest tests/test_state_models.py -q` -> pass（9 passed）
  - [x] 命令3: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 2
子任务: P2-2 统一 preamble 注入
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- utils/skill_preamble.py（新增 preamble 上下文构建与注入工具）
- nodes/plan.py（注入 preamble 到规划提示词）
- nodes/execute.py（注入 preamble 到执行提示词）
- nodes/test.py（注入 preamble 到评审提示词）
- state.py（新增 `session_id/round_id/skill_preamble/preamble_context` 字段）
- tests/test_skill_preamble.py（新增 preamble 注入单测）
- tests/test_state_models.py（补充新增状态字段默认值断言）
- task.md（更新 P2-2 看板与执行记录）
  测试结果:
- python -m pytest tests/test_skill_preamble.py -q -> pass（2 passed）
- python -m pytest tests/test_state_models.py -q -> pass（9 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前 preamble 已注入提示词，但尚未在路由失败场景触发自动降级
- project_profile 在多节点重复读取，后续可在 preamble 层引入缓存复用
- preamble 为文本注入，后续可补结构化 prompt 模板约束
  下一步建议:
- 执行 P2-3：路由失败自动降级到 `legacy_mode`

### P2-3 路由失败自动降级到 `legacy_mode`

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] INFRA [ ] BRIDGE [ ] QUALITY
- 影响文件:
  - [x] `nodes/task_router.py`
  - [x] `tests/test_task_router.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（确认路由接入点在 task_router，且需保留现有复杂度分类）
  - [x] PLAN（接入 `route_skills` 并以 `try/except` 做硬降级）
  - [x] IMPLEMENT（路由异常时强制回退 `legacy_mode`，并写入失败归因）
  - [x] VERIFY（新增并运行 task_router 与 skill_router 相关测试）
  - [x] REPORT（记录降级语义与状态写回字段）
  - [x] HANDOFF（更新主看板与交接信息）

- 降级规则:
  - [x] 当路由器抛出异常时：`run_mode -> legacy_mode`
  - [x] 同步写入：`failure_type=router_failed`
  - [x] 同步写入：`router_decision=skill_router:fallback_legacy(<ErrorType>)`
  - [x] 同步写入：`skill_name=legacy_pipeline`

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_task_router.py -q` -> pass（2 passed）
  - [x] 命令2: `python -m pytest tests/test_skill_router.py -q` -> pass（4 passed）
  - [x] 命令3: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 2
子任务: P2-3 路由失败自动降级
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- nodes/task_router.py（接入 `route_skills`，新增异常降级逻辑）
- tests/test_task_router.py（新增正常路由与异常降级单测）
- task.md（更新 P2-3 看板与执行记录）
  测试结果:
- python -m pytest tests/test_task_router.py -q -> pass（2 passed）
- python -m pytest tests/test_skill_router.py -q -> pass（4 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前降级由 task_router 节点触发，尚未在 graph 层做二次兜底
- 路由异常会覆盖 `failure_type` 为 `router_failed`，后续可考虑保留历史链路
- `force_router_error` 仅用于测试，不应在生产配置中启用
  下一步建议:
- 进入 Phase 3 / P3-1：为 `plan/execute/test/interact/report` 建技能包装层

### P3-1 为 `plan/execute/test/interact/report` 建包装层

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [ ] INFRA [x] BRIDGE [ ] QUALITY
- 影响文件:
  - [x] `utils/skill_bridge.py`
  - [x] `tests/test_skill_bridge.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（确认需保持节点算法不变，仅增加技能包装入口）
  - [x] PLAN（新增桥接模块，统一技能顺序与调度接口）
  - [x] IMPLEMENT（封装 plan/execute/test/interact/report 到 `run_skill`）
  - [x] VERIFY（新增包装层委托测试并运行）
  - [x] REPORT（记录包装层能力与边界）
  - [x] HANDOFF（更新主看板与交接）

- 包装层能力:
  - [x] 提供 `build_base_skill_plan()` 返回基础技能链路顺序
  - [x] 提供 `get_base_skill_handlers()` 统一加载节点处理器
  - [x] 提供 `run_skill(skill_name, state)` 统一调度与 `skill_name` 写回

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_skill_bridge.py -q` -> pass（3 passed）
  - [x] 命令2: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 3
子任务: P3-1 节点技能包装层
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- utils/skill_bridge.py（新增技能包装层与统一调度入口）
- tests/test_skill_bridge.py（新增包装层顺序、委托、异常测试）
- task.md（更新 P3-1 看板与执行记录）
  测试结果:
- python -m pytest tests/test_skill_bridge.py -q -> pass（3 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前仅完成包装层，不包含输入输出契约标准化（P3-2）
- 包装层尚未接入主图执行路径（需后续最小闭环集成）
- `get_base_skill_handlers()` 依赖运行时节点导入，后续可加懒加载缓存
  下一步建议:
- 执行 P3-2：统一技能输入输出契约

### P3-2 统一技能输入输出契约

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [ ] INFRA [x] BRIDGE [ ] QUALITY
- 影响文件:
  - [x] `utils/skill_contract.py`
  - [x] `utils/skill_bridge.py`
  - [x] `tests/test_skill_contract.py`
  - [x] `tests/test_skill_bridge.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（确认包装层已稳定，缺少统一 I/O 契约）
  - [x] PLAN（新增独立契约模块，桥接入口做前后置校验）
  - [x] IMPLEMENT（定义基础技能 required/expected 字段并接入 `run_skill`）
  - [x] VERIFY（运行契约与桥接单测）
  - [x] REPORT（记录契约规则与当前边界）
  - [x] HANDOFF（更新主看板与交接）

- 契约内容:
  - [x] `plan`：输入 `project_path/optimization_goal/current_round`；输出 `current_plan/round_contract`
  - [x] `execute`：输入 `project_path/current_plan`；输出 `code_diff/modified_files`
  - [x] `test`：输入 `project_path/code_diff`；输出 `test_results/build_result/round_evaluation`
  - [x] `interact`：输入 `current_round/max_rounds`；输出 `should_stop/current_round`
  - [x] `report`：输入 `project_path/current_round`；输出 `round_reports/round_history`

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_skill_contract.py -q` -> pass（3 passed）
  - [x] 命令2: `python -m pytest tests/test_skill_bridge.py -q` -> pass（5 passed）
  - [x] 命令3: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 3
子任务: P3-2 技能 I/O 契约统一
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- utils/skill_contract.py（新增技能输入输出契约定义与校验函数）
- utils/skill_bridge.py（`run_skill` 增加输入/输出契约校验）
- tests/test_skill_contract.py（新增契约单测）
- tests/test_skill_bridge.py（补充桥接契约异常测试）
- task.md（更新 P3-2 看板与执行记录）
  测试结果:
- python -m pytest tests/test_skill_contract.py -q -> pass（3 passed）
- python -m pytest tests/test_skill_bridge.py -q -> pass（5 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前契约以 key 存在性校验为主，未做类型与语义完整校验
- 生产图执行链路尚未全面走 `run_skill` 包装入口
- 后续新增技能需同步补充契约表与测试
  下一步建议:
- 执行 P3-3：跑通 `skill_mode` 最小闭环并对照 `legacy_mode`

### P3-3 跑通 `skill_mode` 最小闭环并对照 `legacy_mode`

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [ ] INFRA [x] BRIDGE [ ] QUALITY
- 影响文件:
  - [x] `graph.py`
  - [x] `tests/test_graph.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（确认主图仍为 legacy 调用，需在图层接入 skill 调度）
  - [x] PLAN（新增分发器：skill_mode 走 `run_skill`，失败自动回退 legacy）
  - [x] IMPLEMENT（plan/execute/test/report/interact 节点接入 skill dispatcher）
  - [x] VERIFY（新增分发器对照与回退测试并运行）
  - [x] REPORT（记录最小闭环行为与对照结论）
  - [x] HANDOFF（更新主看板与交接信息）

- 闭环与对照结果:
  - [x] `legacy_mode`：继续使用原节点函数执行
  - [x] `skill_mode`：通过 `run_skill` 进入技能包装层执行
  - [x] 当技能分发失败时：自动降级到 `legacy_mode`，并保留执行连续性
  - [x] 对照测试显示：在同等处理逻辑下 `legacy_mode` 与 `skill_mode` 结果标记一致

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_graph.py -q` -> pass（10 passed）
  - [x] 命令2: `python -m pytest tests/test_skill_bridge.py -q` -> pass（5 passed）
  - [x] 命令3: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 3
子任务: P3-3 skill_mode 最小闭环与对照
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- graph.py（新增 `_build_skill_dispatcher`，核心节点接入 skill/legacy 双路径）
- tests/test_graph.py（新增 skill_dispatcher 传统路径、对照一致性、失败回退测试）
- task.md（更新 P3-3 看板与执行记录）
  测试结果:
- python -m pytest tests/test_graph.py -q -> pass（10 passed）
- python -m pytest tests/test_skill_bridge.py -q -> pass（5 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前闭环以图层分发器实现，尚未把 archive/task_router 纳入技能包装层
- `run_skill` 失败后会回退 legacy，可能掩盖部分契约问题，需要后续观测告警
- 真实端到端任务级对照（含文件修改与测试耗时）仍需在 Phase 5 集成测试补齐
  下一步建议:
- 进入 Phase 4 / P4-1：建立 `skills/*.md.tmpl` 或扩展 `opcskills` 模板能力

### P4-1 建立 `skills/*.md.tmpl` 或扩展 `opcskills` 模板能力

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] INFRA [ ] BRIDGE [ ] QUALITY
- 影响文件:
  - [x] `skills/skill_doc.md.tmpl`
  - [x] `utils/skill_doc_template.py`
  - [x] `tests/test_skill_doc_template.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（确认当前无 `skills/*.md.tmpl`，需先落模板底座）
  - [x] PLAN（新增模板目录与渲染工具，供 P4-2 复用）
  - [x] IMPLEMENT（建立通用 `skill_doc.md.tmpl` 与 `render_template` 能力）
  - [x] VERIFY（新增模板加载/渲染/缺失字段测试并运行）
  - [x] REPORT（记录模板规范与接口边界）
  - [x] HANDOFF（更新主看板与交接信息）

- 模板能力:
  - [x] 建立 `skills/skill_doc.md.tmpl` 通用技能文档模板
  - [x] 提供 `get_skill_templates_dir/load_template/render_template` 工具
  - [x] 渲染阶段对缺失上下文字段抛出明确错误

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_skill_doc_template.py -q` -> pass（4 passed）
  - [x] 命令2: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 4
子任务: P4-1 技能文档模板底座
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- skills/skill_doc.md.tmpl（新增技能文档模板）
- utils/skill_doc_template.py（新增模板目录解析、加载与渲染工具）
- tests/test_skill_doc_template.py（新增模板渲染测试）
- task.md（更新 P4-1 看板与执行记录）
  测试结果:
- python -m pytest tests/test_skill_doc_template.py -q -> pass（4 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前仅完成模板底座，尚未提供批量文档生成脚本（P4-2）
- 模板渲染目前使用 `str.format`，后续可评估更强模板引擎
- 尚未对模板与技能注册表的一致性做自动检查（P4-3）
  下一步建议:
- 执行 P4-2：实现 `scripts/gen_skill_docs.py`

### P4-2 实现 `scripts/gen_skill_docs.py`

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] INFRA [ ] BRIDGE [ ] QUALITY
- 影响文件:
  - [x] `scripts/gen_skill_docs.py`
  - [x] `tests/test_gen_skill_docs.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（确认可复用 `skill_registry/skill_contract/skill_doc_template`）
  - [x] PLAN（实现最小生成脚本：注册中心 + 契约 + 模板渲染）
  - [x] IMPLEMENT（新增 `gen_skill_docs.py` 并输出核心技能文档）
  - [x] VERIFY（新增并运行脚本测试 + 模板回归测试）
  - [x] REPORT（记录输出目录、覆盖范围与边界）
  - [x] HANDOFF（更新主看板与交接信息）

- 脚本能力:
  - [x] 支持 CLI 参数 `--output-dir` 与 `--include-disabled`
  - [x] 默认输出到 `skills/generated`
  - [x] 基于 `build_core_skill_registry + get_skill_contract + render_template` 生成文档
  - [x] 每个技能输出 `*.md`，包含元数据、输入输出、失败处理说明

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_gen_skill_docs.py -q` -> pass（1 passed）
  - [x] 命令2: `python -m pytest tests/test_skill_doc_template.py -q` -> pass（4 passed）
  - [x] 命令3: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 4
子任务: P4-2 技能文档生成脚本
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- scripts/gen_skill_docs.py（新增技能文档生成脚本）
- tests/test_gen_skill_docs.py（新增文档生成脚本测试）
- task.md（更新 P4-2 看板与执行记录）
  测试结果:
- python -m pytest tests/test_gen_skill_docs.py -q -> pass（1 passed）
- python -m pytest tests/test_skill_doc_template.py -q -> pass（4 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前生成范围为 core skills（plan/execute/test/report），后续技能需扩展注册源
- 文档内容仍基于静态契约，未附带运行指标或真实示例输入输出
- 生成脚本尚未与 CI freshness 校验联动（P4-3）
  下一步建议:
- 执行 P4-3：增加文档新鲜度检查命令并接入 CI

### P4-3 增加文档新鲜度检查命令并接入 CI

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] QUALITY [ ] INFRA [ ] BRIDGE
- 影响文件:
  - [x] `scripts/check_skill_docs_freshness.py`
  - [x] `.github/workflows/ci.yml`
  - [x] `tests/test_check_skill_docs_freshness.py`
  - [x] `skills/generated/plan.md`
  - [x] `skills/generated/execute.md`
  - [x] `skills/generated/test.md`
  - [x] `skills/generated/report.md`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（确认 P4-2 已有生成脚本，缺失 freshness 校验与 CI 接入）
  - [x] PLAN（新增对比脚本：已提交文档 vs 临时再生成文档）
  - [x] IMPLEMENT（新增 freshness 脚本、接入 CI、补齐生成文档基线）
  - [x] VERIFY（运行 freshness 测试、生成脚本测试与实际检查命令）
  - [x] REPORT（记录校验规则与 CI 门禁位置）
  - [x] HANDOFF（更新主看板与交接信息）

- 新鲜度校验能力:
  - [x] 缺失文件检测（Missing generated doc）
  - [x] 多余文件检测（Unexpected generated doc）
  - [x] 内容漂移检测（Outdated generated doc）
  - [x] 提供失败提示命令：`python scripts/gen_skill_docs.py`

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_check_skill_docs_freshness.py -q` -> pass（2 passed）
  - [x] 命令2: `python -m pytest tests/test_gen_skill_docs.py -q` -> pass（1 passed）
  - [x] 命令3: `python scripts/check_skill_docs_freshness.py` -> pass（Skill docs are fresh）
  - [x] 命令4: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 4
子任务: P4-3 文档新鲜度检查与 CI 接入
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- scripts/check_skill_docs_freshness.py（新增 freshness 对比脚本）
- .github/workflows/ci.yml（新增生成文档新鲜度检查步骤）
- tests/test_check_skill_docs_freshness.py（新增新鲜度校验测试）
- scripts/gen_skill_docs.py（修复脚本直跑导入路径）
- skills/generated/*.md（新增生成文档基线）
- task.md（更新 P4-3 看板与执行记录）
  测试结果:
- python -m pytest tests/test_check_skill_docs_freshness.py -q -> pass（2 passed）
- python -m pytest tests/test_gen_skill_docs.py -q -> pass（1 passed）
- python scripts/check_skill_docs_freshness.py -> pass（Skill docs are fresh）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前 freshness 仅校验 `skills/generated`，未来新增分组文档需扩展检查范围
- 校验依赖本地模板/契约稳定，模板字段变化会触发大范围文档更新
- CI 仅做校验，不自动修复，需开发者手动执行生成脚本
  下一步建议:
- 进入 Phase 5 / P5-1：补齐技能级单元测试

### P5-1 技能级单元测试补齐

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] QUALITY [ ] INFRA [ ] BRIDGE
- 影响文件:
  - [x] `tests/test_skill_router.py`
  - [x] `tests/test_skill_preamble.py`
  - [x] `tests/test_skill_contract.py`
  - [x] `tests/test_skill_bridge.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（盘点技能级测试缺口，聚焦边界场景）
  - [x] PLAN（补 router/preamble/contract/bridge 四类单测）
  - [x] IMPLEMENT（新增 7 个边界测试用例）
  - [x] VERIFY（运行技能级测试集合并检查诊断）
  - [x] REPORT（记录覆盖补齐范围）
  - [x] HANDOFF（更新主看板与交接）

- 补齐点:
  - [x] `skill_router`：非法 `run_mode` 回退 legacy；Rust 文档目标不走 fast-path
  - [x] `skill_preamble`：默认 timeout/profile 值断言
  - [x] `skill_contract`：未知技能契约查询报错
  - [x] `skill_bridge`：`run_skill` 对原始 state 引用一致性

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_skill_router.py tests/test_skill_preamble.py tests/test_skill_contract.py tests/test_skill_bridge.py -q` -> pass（19 passed）
  - [x] 命令2: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 5
子任务: P5-1 技能级单元测试补齐
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- tests/test_skill_router.py（新增路由回退与风险约束测试）
- tests/test_skill_preamble.py（新增默认配置注入测试）
- tests/test_skill_contract.py（新增未知契约报错测试）
- tests/test_skill_bridge.py（新增 state 引用一致性测试）
- task.md（更新 P5-1 看板与执行记录）
  测试结果:
- python -m pytest tests/test_skill_router.py tests/test_skill_preamble.py tests/test_skill_contract.py tests/test_skill_bridge.py -q -> pass（19 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前仍以单元测试为主，尚未覆盖技能链路跨节点集成行为（P5-2）
- 回归对照测试尚未补齐到完整 legacy_mode 运行路径（P5-3）
- 后续新增技能功能需同步扩展契约与路由测试
  下一步建议:
- 执行 P5-2：技能链路集成测试补齐

### P5-2 技能链路集成测试补齐

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] QUALITY [ ] INFRA [ ] BRIDGE
- 影响文件:
  - [x] `tests/test_skill_chain_integration.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（确认需补齐跨技能链路级别的行为验证）
  - [x] PLAN（设计成功链路 + 契约破坏中断两条集成路径）
  - [x] IMPLEMENT（新增 `test_skill_chain_integration.py`）
  - [x] VERIFY（运行链路集成测试并检查诊断）
  - [x] REPORT（记录链路级保障能力）
  - [x] HANDOFF（更新主看板与交接）

- 集成覆盖点:
  - [x] 成功链路：`plan -> execute -> test -> interact -> report` 端到端契约贯通
  - [x] 失败链路：`execute` 输出契约缺失时链路抛错并中断

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_skill_chain_integration.py -q` -> pass（2 passed）
  - [x] 命令2: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 5
子任务: P5-2 技能链路集成测试补齐
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- tests/test_skill_chain_integration.py（新增技能链路成功/失败集成测试）
- task.md（更新 P5-2 看板与执行记录）
  测试结果:
- python -m pytest tests/test_skill_chain_integration.py -q -> pass（2 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前集成为“伪 handler”链路，尚未覆盖真实节点内外部依赖交互
- 主图完整运行态对照仍需在 P5-3 补齐 legacy_mode 回归测试
- 后续新增技能节点需同步补齐链路集成案例
  下一步建议:
- 执行 P5-3：`legacy_mode` 回归对照测试补齐

### P5-3 `legacy_mode` 回归对照测试补齐

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] QUALITY [ ] INFRA [ ] BRIDGE
- 影响文件:
  - [x] `tests/test_legacy_mode_regression.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（确认需补齐 legacy_mode 全核心技能回归对照）
  - [x] PLAN（覆盖全核心技能 legacy 路径 + skill 运行异常隔离）
  - [x] IMPLEMENT（新增 `test_legacy_mode_regression.py`）
  - [x] VERIFY（运行 legacy 回归测试与 graph 回归测试）
  - [x] REPORT（记录 legacy 稳定性结论）
  - [x] HANDOFF（更新主看板与交接）

- 回归覆盖点:
  - [x] 核心技能 `plan/execute/test/report/interact` 在 `legacy_mode` 下均走 legacy handler
  - [x] 即使 skill runtime 异常，`legacy_mode` 仍保持可执行且不污染失败类型

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_legacy_mode_regression.py -q` -> pass（6 passed）
  - [x] 命令2: `python -m pytest tests/test_graph.py -q` -> pass（10 passed）
  - [x] 命令3: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 5
子任务: P5-3 legacy_mode 回归对照测试
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- tests/test_legacy_mode_regression.py（新增 legacy_mode 回归对照测试）
- task.md（更新 P5-3 看板与执行记录）
  测试结果:
- python -m pytest tests/test_legacy_mode_regression.py -q -> pass（6 passed）
- python -m pytest tests/test_graph.py -q -> pass（10 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前回归仍是调度层/伪 handler 验证，真实节点外部依赖仍需专项回归
- 若后续引入更多技能节点，需同步扩展 legacy 回归矩阵
- 建议在 CI 中独立分组 skill/legacy 对照测试以便快速定位
  下一步建议:
- 进入 Phase 6 / P6-1：灰度开关接入（CLI + 环境变量）

### P6-1 灰度开关接入（CLI + 环境变量）

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] INFRA [ ] BRIDGE [ ] QUALITY
- 影响文件:
  - [x] `main.py`
  - [x] `tests/test_run_mode_rollout.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（确认当前仅支持固定 run_mode，缺少灰度百分比分流）
  - [x] PLAN（显式 run_mode 保持最高优先级，灰度作为兜底分流）
  - [x] IMPLEMENT（新增 CLI/ENV 灰度参数并接入 `_resolve_run_mode`）
  - [x] VERIFY（新增 run_mode 分流测试并回归 graph 测试）
  - [x] REPORT（记录分流优先级与可复现策略）
  - [x] HANDOFF（更新主看板与交接）

- 灰度能力:
  - [x] CLI 开关：`--skill-gray-percent`（0~100）
  - [x] 环境变量：`OPC_SKILL_GRAY_PERCENT`
  - [x] 优先级：`--run-mode` > `OPC_RUN_MODE` > gray percent 分流 > `legacy_mode`
  - [x] 灰度分流：基于 `project_path|goal` 的哈希桶，结果可复现

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_run_mode_rollout.py -q` -> pass（5 passed）
  - [x] 命令2: `python -m pytest tests/test_graph.py -q` -> pass（10 passed）
  - [x] 命令3: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 6
子任务: P6-1 灰度开关接入
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- main.py（新增 `--skill-gray-percent` 与 `OPC_SKILL_GRAY_PERCENT` 分流逻辑）
- tests/test_run_mode_rollout.py（新增 run_mode 优先级/灰度分流测试）
- task.md（更新 P6-1 看板与执行记录）
  测试结果:
- python -m pytest tests/test_run_mode_rollout.py -q -> pass（5 passed）
- python -m pytest tests/test_graph.py -q -> pass（10 passed）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 灰度分流当前按 `project_path|goal` 哈希，无法按用户/租户维度精细控制
- 仅接入模式分流，P6-2 仍需观察真实运行数据再决定默认切换
- 若 `project_path` 或 `goal` 频繁变化，单项目运行模式可能在不同任务间变化
  下一步建议:
- 执行 P6-2：运行数据观察与评估

### P6-2 运行数据观察与评估

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] QUALITY [ ] INFRA [ ] BRIDGE
- 影响文件:
  - [x] `scripts/evaluate_rollout.py`
  - [x] `tests/test_rollout_evaluation.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（确认 metrics 已包含 run_mode/failure_type，可做灰度评估）
  - [x] PLAN（定义评估结果：insufficient_data/continue_gray/rollback/promote）
  - [x] IMPLEMENT（新增 rollout 评估脚本与 JSON 输出）
  - [x] VERIFY（运行评估脚本测试与命令行验证）
  - [x] REPORT（记录评估规则与当前样本结论）
  - [x] HANDOFF（更新主看板与交接信息）

- 评估能力:
  - [x] 读取 `.opclog/metrics.jsonl` 计算 skill/legacy 样本占比与失败率
  - [x] 输出推荐决策：`insufficient_data` / `continue_gray` / `rollback_skill` / `promote_skill_default`
  - [x] 输出 `rollout_evaluation.json` 供后续决策与审计复用

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_rollout_evaluation.py -q` -> pass（3 passed）
  - [x] 命令2: `python scripts/evaluate_rollout.py --project-path .` -> pass（recommendation=insufficient_data）
  - [x] 命令3: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 6
子任务: P6-2 运行数据观察与评估
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- scripts/evaluate_rollout.py（新增 rollout 评估脚本）
- tests/test_rollout_evaluation.py（新增评估规则测试）
- task.md（更新 P6-2 看板与执行记录）
  测试结果:
- python -m pytest tests/test_rollout_evaluation.py -q -> pass（3 passed）
- python scripts/evaluate_rollout.py --project-path . -> pass（recommendation=insufficient_data）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前项目样本轮次不足，评估结果为 `insufficient_data`
- 评估规则为阈值策略，后续可结合时间窗口与指标趋势进一步细化
- 仍需在 P6-3 将评估输出转化为默认模式切换与回退执行方案
  下一步建议:
- 执行 P6-3：默认模式切换决策与回退预案

### P6-3 默认模式切换决策与回退预案

- 状态: [ ] 未开始 [ ] 进行中 [x] 已完成 [ ] 阻塞
- 类型: [x] INFRA [ ] BRIDGE [ ] QUALITY
- 影响文件:
  - [x] `scripts/decide_rollout_mode.py`
  - [x] `tests/test_rollout_decision_plan.py`
  - [x] `task.md`

- Task Checklist:
  - [x] ANALYZE 完成
  - [x] PLAN 完成
  - [x] IMPLEMENT 完成
  - [x] VERIFY 完成
  - [x] REPORT 完成
  - [x] HANDOFF 完成

- 执行清单:
  - [x] ANALYZE（确认已有评估结果，缺少“执行决策 + 回退预案”落地产物）
  - [x] PLAN（将评估 recommendation 映射为 run_mode/灰度百分比/env 计划）
  - [x] IMPLEMENT（新增决策脚本并输出 `rollout_decision.json`）
  - [x] VERIFY（运行决策测试与脚本命令行验证）
  - [x] REPORT（记录决策映射规则与回退动作）
  - [x] HANDOFF（更新主看板与交接信息）

- 决策与回退能力:
  - [x] 根据评估结果输出目标模式与灰度百分比
  - [x] 生成环境变量执行计划（`OPC_RUN_MODE` / `OPC_SKILL_GRAY_PERCENT`）
  - [x] 生成回退触发条件、立即动作、验证命令
  - [x] 输出 `.opclog/rollout_decision.json` 供运维与审计复用

- 验证记录:
  - [x] 命令1: `python -m pytest tests/test_rollout_decision_plan.py -q` -> pass（3 passed）
  - [x] 命令2: `python scripts/decide_rollout_mode.py --project-path .` -> pass（rollout_action=collect_more_data）
  - [x] 命令3: `GetDiagnostics` -> pass（0 diagnostics）

- 结论:
  - [x] 可合并
  - [x] 需继续
  - [ ] 已阻塞（需人工决策）

【Task Handoff】
阶段: Phase 6
子任务: P6-3 默认模式切换与回退预案
状态: done
Checklist:

- [x] ANALYZE
- [x] PLAN
- [x] IMPLEMENT
- [x] VERIFY
- [x] REPORT
- [x] HANDOFF
      代码改动:
- scripts/decide_rollout_mode.py（新增 rollout 决策与回退预案生成脚本）
- tests/test_rollout_decision_plan.py（新增决策映射测试）
- task.md（更新 P6-3 看板与执行记录）
  测试结果:
- python -m pytest tests/test_rollout_decision_plan.py -q -> pass（3 passed）
- python scripts/decide_rollout_mode.py --project-path . -> pass（rollout_action=collect_more_data）
- GetDiagnostics -> pass（0 diagnostics）
  风险与注意:
- 当前决策仍基于阈值映射规则，样本不足时仅给出保守策略
- 回退动作以环境变量切换为主，生产发布流程仍需结合实际部署系统
- 后续建议将决策脚本输出接入发布流水线审批节点
  下一步建议:
- 可进入运维执行阶段：按 `rollout_decision.json` 执行灰度与回退控制

## 12. Definition of Done（任务完成判定）

子任务可标记 `done` 必须同时满足：

- 代码实现完成且边界清晰。
- 目标验证通过（测试或等效验证）。
- 无新增明显诊断错误。
- 本文件“Phase 任务看板”已勾选对应项。
- 已输出 `Task Handoff`。
- `Task Checklist` 六项均为 `[x]`。

未满足任一项，只能标记 `partial` 或 `blocked`。
