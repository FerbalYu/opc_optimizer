# OPC Local Optimizer 阶段计划

> 代码路径：`D:\workflow\opc\src\local_optimizer`
> 更新时间：2026-03-25
> 当前里程碑：Step 23 已完成，Web UI 计划审核流已落首版

---

## 当前结论

前 18 步把 OPC 做成了“能规划、能执行、能测试、能展示”的本地优化器。

19 到 23 步的目标，是把它从“会改代码”提升到“每轮都围绕高价值目标认真工作”。这部分现在已经完成核心落地：

- 每轮改动先形成结构化合同，而不是松散建议
- 执行只能尽量围绕合同允许的文件和预期差异展开
- 测试会判断目标是否真正完成，而不是只看没报错
- 低价值回合会被识别并要求重规划
- 复盘和报告使用真实 diff 证据，而不是只看模型自述

---

## 已完成步骤

| Step | 状态 | 说明 |
|------|------|------|
| 17 | 已完成 | Context7 文档辅助执行 |
| 18 | 已完成 | Playwright UI 验证 |
| 19 | 已完成 | Round Contract 结构化规划 |
| 20 | 已完成 | Plan-to-Diff Alignment Gate |
| 21 | 已完成 | Goal Completion Evaluation |
| 22 | 已完成 | Low-Value Round Detection And Replan |
| 23 | 已完成 | Diff-Based Review |

---

## Step 19: Round Contract Planning

### 目标

让每一轮只承接一个主任务，并输出机器可消费的计划结构。

### 已落地

- `nodes/plan.py` 输出 `round_contract`
- 合同字段包括：
  - `round_objective`
  - `current_state_assessment`
  - `target_files`
  - `acceptance_checks`
  - `expected_diff`
  - `risk_level`
  - `fallback_if_blocked`
  - `impact_score`
  - `confidence_score`
  - `verification_score`
  - `effort_score`
- 合同会写入目标项目 `.opclog/round_contract.json`
- `plan.md` 现在本质上是合同的可读渲染结果

### 结果

- 计划不再只是自然语言摘要
- 后续节点可以直接使用合同字段，不必重复猜测计划意图

---

## Step 20: Plan-to-Diff Alignment Gate

### 目标

阻止“改了，但和本轮目标关系不大”的回合被计为有效进展。

### 已落地

- `nodes/execute.py` 优先读取合同约束的 `target_files`
- 允许执行的文件范围会从 `round_contract` 派生
- `expected_diff` 中标为不需要变更的条目，不会被当成必改对象
- 执行 prompt 会直接注入合同 JSON、验收项和预期改动

### 结果

- 执行节点更难随意扩散到无关文件
- 改动和本轮计划之间的对应关系更强

---

## Step 21: Goal Completion Evaluation

### 目标

让测试阶段评估“价值交付”而不只是“技术上没炸”。

### 已落地

- `nodes/test.py` 生成 `round_evaluation`
- 评估维度包含：
  - `goal_completed`
  - `value_delivered`
  - `aligned_with_plan`
  - `low_value_round`
  - `replan_required`
  - `reasons`
  - `summary`
- 如果本轮没有真实命中目标，哪怕构建不报错，也可能被判定为低价值回合

### 结果

- “安全但没价值”的回合不能再轻易过关

---

## Step 22: Low-Value Round Detection And Replan

### 目标

当回合落成碎修、注释改动、边角清理时，系统能自动纠偏。

### 已落地

- `round_evaluation.low_value_round` 和 `round_evaluation.replan_required` 进入主流程判断
- `nodes/interact.py` 会根据评估结果决定更强的继续/重规划提示
- `nodes/report.py` 会把这类判断写入每轮报告

### 结果

- 系统更偏向“承认本轮价值不足，再来一轮”
- 不再把所有完成的 diff 都当成有效优化

---

## Step 23: Diff-Based Review Instead Of Summary-Based Review

### 目标

复盘必须基于真实代码变化，而不是相信模型自我总结。

### 已落地

- 复盘读取 `.bak` 与当前文件的真实差异
- 报告中新增 `Diff Evidence`
- 交互输出中新增 `Final Diff Evidence`
- 评审会结合：
  - `round_contract`
  - 真实 before/after 代码差异
  - 本轮测试/构建结果
  - `round_evaluation`

### 结果

- 可以明确回答“这轮到底修了什么”
- 下一轮继续还是换任务，有了更可靠的证据基础

---

## Web UI 审核流

这是用户新增的能力需求，目前已经做出首版实现。

### 需求

- 先展示 AI 生成的优化列表
- 用户如果在开始时勾选“不审核”，则全自动执行
- 否则每轮任务出来后，需要用户查看哪些能做、哪些不做
- 如果本批全部不合适，可以整批否决并让系统换一批
- 工作中任务要以任务栏形式展示，并可点击查看详情

### 已落地

- `main.py` 支持从 Web UI 读取 `skip_plan_review`
- `state.py` / `checkpoint.py` 新增：
  - `active_tasks`
  - `ui_preferences`
- `nodes/plan.py` 新增：
  - `_build_review_tasks`
  - `_filter_contract_by_selected_tasks`
  - `_review_contract_with_web_ui`
- Web UI 事件新增：
  - `task_plan_active`
  - `plan_review_required`
  - `plan_review_result`
- 前端已支持：
  - landing 勾选跳过审核
  - 任务审核弹窗
  - 顶部任务条
  - 任务详情弹窗

### 当前状态

- 后端逻辑已接通
- 前端交互已实现首版
- 仍需要更完整的端到端联调与体验打磨

---

## 下一步

### Step 24: Verification-First Mode For High-Risk Logic

- 对高风险核心逻辑，先补最小可执行验证，再允许大改
- 避免在没有任何可信验证的情况下重写关键算法

### Step 25: Efficiency Upgrade Pass

- 更小的目标文件白名单
- 更严格的上下文预算
- 提前跳过低信号文件
- 避免每轮把整项目分析重复喂给模型

### Step 26: Web UI 审核流联调与完成态

- 补完 landing / dashboard 的显示一致性
- 跑通“审批部分任务 / 全部驳回重来 / 任务详情查看”全链路
- 让任务审核流成为默认可用的稳态功能，而不是只停留在首版

---

## 本轮文档同步说明

这次更新的重点不是继续写愿景，而是把已经落地的代码行为和文档统一起来：

- `README.md` 已同步 step 19-23 与 Web UI 审核流
- `roadmap.md` 改为只描述 24-26 的后续方向
- `version_evaluation.md` 改为评估当前真实状态
- `docs/` 下流程文档已改成当前实现视角

