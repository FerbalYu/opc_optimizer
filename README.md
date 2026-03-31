# OPC 本地代码优化器

基于 [LangGraph](https://github.com/langchain-ai/langgraph) 的多轮自动代码优化工作流。给定一个目标项目目录和优化目标，它会持续循环执行以下节点直到达到停止条件：

```
Plan → Execute → Test → Archive → Report → Interact
```

每轮严格围绕一份"轮次合同"（`round_contract`）运行：规划节点生成合同，执行节点仅改动合同允许的目标文件，测试节点同时跑构建/测试/UI 验证并对本轮价值打分，低价值或偏题的轮次会触发重规划。

---

## 架构概览

```
main.py               CLI 入口 & Web UI 启动
graph.py              LangGraph 工作流定义（节点注册 + 条件边）
state.py              OptimizerState 类型定义（TypedDict）

nodes/
  plan.py             规划节点：生成 round_contract，支持 Web UI 审核
  execute.py          执行节点：SEARCH/REPLACE 格式改动、沙箱验证、自动格式化
  test.py             测试节点：构建/测试/UI 验证、价值评估、自动回滚
  archive.py          归档节点：每 N 轮压缩历史
  report.py           报告节点：生成每轮 Markdown 报告
  interact.py         交互节点：CLI / Web UI 继续/停止/回滚/调整目标

utils/
  llm.py              LLMService（litellm 封装，支持多模型）
  project_profile.py  项目类型检测（规则表 + LLM 兜底，带缓存）
  code_graph.py       代码符号索引（减少 token 消耗）
  diff_parser.py      SEARCH/REPLACE 解析 + 模糊匹配
  formatter.py        自动检测并运行项目格式化工具
  context7_client.py  Context7 文档查询（为执行节点提供框架文档）
  skill_loader.py     加载 opcskills/ 中的优化策略提示
  checkpoint.py       断点续跑
  telemetry.py        OpenTelemetry 追踪（可选）
  trace_logger.py     LLM 调用追踪日志
  config_loader.py    YAML 配置加载（项目级 + 全局）
  context_pruner.py   对话上下文压缩
  git_ops.py          Git 操作工具
  file_ops.py         文件读写工具

plugins/
  __init__.py         插件 BaseNode 接口 + 自动发现逻辑
  test_gen_plugin.py  内置示例插件（测试生成）

opcskills/            针对不同语言/框架的优化策略 Markdown 文件
  python-performance.md
  javascript-performance.md
  vue-optimization.md
  react-patterns.md
  go-performance.md
  clean-code.md
  security-checklist.md

ui/
  tui.py              终端 UI（彩色打印）
  web_server.py       WebSocket + HTTP 服务器
  web/
    index.html        运行中看板（3D Web UI）
    landing.html      启动配置页
```

---

## 节点说明

### `plan` — 规划节点
- 加载项目类型画像（`project_profile`）和 SKILL 优化策略
- 通过 Code Graph 提取符号摘要，减少提示 token
- LLM 生成结构化 `round_contract`（目标文件、验收条件、期望 diff、风险等级、评分）
- 写入 `.opclog/plan.md` 和 `.opclog/round_contract.json`
- 如有 Web UI 客户端连接且未跳过审核，暂停等待用户批准任务列表

### `execute` — 执行节点
- 读取 `round_contract.target_files` 确定可改文件范围
- 通过 Context7 拉取相关框架文档作为参考
- LLM 以 `SEARCH/REPLACE` 格式输出代码修改
- 对每次修改：路径白名单过滤 → 模糊匹配 → 代码安全审查 → 沙箱编译（.py 文件）→ 写入并备份（`.bak`）→ 自动格式化
- 生成 `.opclog/CHANGELOG.md` 追加记录

### `test` — 测试节点
- 依次运行：`build_cmd`（构建）、`test_cmd`（测试）、UI 验证（Playwright，需 `OPC_ENABLE_UI_CHECK=1`）
- 对本轮结果进行 `round_evaluation` 评估（目标完成度、价值评分、合同对齐度）
- 构建失败时自动回滚 `.bak` 备份文件
- LLM 审查真实 diff 证据并生成下一轮优化建议，写入 `.opclog/suggestions.md`

### `archive` — 归档节点
每 N 轮（默认 3 轮）压缩历史数据，避免上下文膨胀。

### `report` — 报告节点
为每轮生成 Markdown 格式报告，保存至 `.opclog/轮次报告/`。

### `interact` — 交互节点
- 检查停止条件：达到最大轮数、连续 2 轮无改进
- `auto` 模式：自动继续
- Web UI 模式：推送 `awaiting_input` 事件，支持继续/停止/回滚/调整目标
- CLI 模式：`[c] 继续 / [s] 停止 / [a] 调整目标`

---

## 快速开始

**要求：** Python 3.10+

```bash
cd d:\workflow\opc\src\local_optimizer

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

配置 `.env`（参考 `.env.example`）：

```ini
OPENAI_API_KEY=your_api_key_here
OPENAI_API_BASE=https://api.minimaxi.com/v1   # 或任何兼容 OpenAI 格式的接口
DEFAULT_LLM_MODEL=MiniMax-M2.7
```

---

## 运行命令

```bash
# 基本运行
python main.py D:\your-project --goal "提升代码质量与可维护性"

# 最大 5 轮，全自动（无交互）
python main.py D:\your-project --goal "持续优化" --auto --max-rounds 5

# 断点续跑
python main.py D:\your-project --goal "持续优化" --resume

# 模拟执行（不修改文件）
python main.py D:\your-project --goal "分析" --dry-run

# 启动 Web UI（浏览器端配置并运行）
python main.py --web-ui

# 指定端口
python main.py --web-ui --http-port 8765

# 分模型配置（规划/执行/测试用不同模型）
python main.py D:\your-project --goal "优化" \
  --plan-model openai/gpt-4o \
  --execute-model openai/gpt-4o-mini \
  --test-model openai/gpt-4o-mini

# 指定格式化工具
python main.py D:\your-project --goal "优化" --formatter "ruff format"
python main.py D:\your-project --goal "优化" --no-format    # 禁用自动格式化
```

---

## 命令行参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `project_path` | — | 目标项目绝对路径（`--web-ui` 独立模式时可省略）|
| `--goal` | `"Improve code quality..."` | 优化目标描述 |
| `--max-rounds` | `5` | 最大优化轮数 |
| `--archive-every` | `3` | 每 N 轮归档一次历史 |
| `--auto` | false | 全自动模式，跳过交互 |
| `--resume` | false | 从最近断点续跑 |
| `--dry-run` | false | 模拟执行，不写入文件 |
| `--model` | `.env` 中的值 | 全局 LLM 模型（litellm 格式）|
| `--plan-model` | — | 规划节点专用模型 |
| `--execute-model` | — | 执行节点专用模型 |
| `--test-model` | — | 测试节点专用模型 |
| `--timeout` | `120` | LLM 调用超时（秒）|
| `--web-ui` | false | 启动 Web UI 看板 |
| `--http-port` | `8765` | Web UI HTTP 端口（WS 端口 = HTTP + 1）|
| `--formatter` | 自动检测 | 显式指定格式化命令 |
| `--no-format` | false | 禁用写入后自动格式化 |

---

## YAML 配置文件

在目标项目根目录创建 `opc.config.yaml` 可覆盖 CLI 默认值。优先级：

```
CLI 参数 > 项目 opc.config.yaml > 全局 ~/.opc/config.yaml > 默认值
```

参见 [`opc.config.example.yaml`](opc.config.example.yaml) 了解可用字段（`goal`、`max_rounds`、`auto`、`dry_run`、`timeout`、`build_timeout`、`log_level`、`max_file_size`、`allowed_extensions`）。

---

## Web UI 审核流

启动时若不带 `project_path` 则进入 landing 配置页，可在浏览器中填写项目路径、目标、轮数及模型。

运行期间看板展示每个节点的进度、耗时和 diff。每轮计划生成后：

- **勾选"跳过审核"**：`skip_plan_review=true`，计划自动进入执行
- **不勾选**：展示任务列表，用户选择允许执行的任务后发送 `approve_plan`；全部否决则发送 `replan_plan`，LLM 重新生成任务批次

看板还支持运行中实时发送：继续 / 停止 / 回滚 / 调整目标。

---

## 项目类型感知

`utils/project_profile.py` 通过规则表（优先）和 LLM 检测（兜底）识别项目类型，支持：

`python` · `javascript` · `vue` · `react` · `go` · `rust` · `java` · `csharp` · `flutter` · `ruby` · `微信小程序`

检测结果缓存至 `.opclog/.project_profile.json`（根目录变化哈希失效）。画像包含：扫描扩展名、构建/测试/Dev 命令、格式化工具、忽略目录、优化建议。

---

## 插件系统

在目标项目的 `opc_plugins/` 目录下创建 Python 文件，继承 `BaseNode` 即可注入自定义节点：

```python
# opc_plugins/lint_node.py
from plugins import BaseNode

class LintNode(BaseNode):
    name = "lint"
    insert_after = "test"   # 插入在哪个内置节点之后

    def run(self, state: dict) -> dict:
        # 执行 lint，更新 state
        return state
```

运行时 `discover_plugins()` 自动发现并按 `insert_after` 注入工作流。

---

## SKILL 优化策略

`opcskills/` 目录下的 `.md` 文件会在规划阶段加载，为 LLM 提供特定语言/框架的优化提示（如 `python-performance.md`、`vue-optimization.md`、`security-checklist.md`）。可直接编辑或新增 `.md` 文件来扩展策略库。

---

## 安全机制

| 机制 | 说明 |
|---|---|
| 路径白名单 | 执行节点只改 `round_contract.target_files` 允许的文件 |
| 路径穿越防护 | 拒绝绝对路径和 `../` 路径 |
| `.bak` 备份 | 每次写入前备份原文件，构建失败时自动回滚 |
| 沙箱编译 | Python 文件写入前在临时目录 `compile()` 验证语法 |
| 代码审查 | `CodeReviewer` 检测生成代码中的可疑模式 |
| 子进程白名单 | `test.py` 只允许运行 `ALLOWED_COMMANDS` 中的命令 |
| 环境变量清理 | 子进程剥离 `LD_PRELOAD` 等危险环境变量 |
| 模糊匹配阈值 | 低置信度的代码替换需用户确认（非 auto 模式）|

---

## 关键产物（`.opclog/`）

运行后会在目标项目下生成：

| 文件 | 说明 |
|---|---|
| `plan.md` | 当前轮结构化计划文本 |
| `round_contract.json` | 当前轮机器可读合同 |
| `suggestions.md` | 测试节点给出的下轮优化建议 |
| `CHANGELOG.md` | 每轮改动追加记录 |
| `final_report.md` | 流程结束时的最终报告 |
| `checkpoint.json` | 断点续跑状态 |
| `.project_profile.json` | 项目类型画像缓存 |
| `轮次报告/` | 每轮独立 Markdown 报告 |
| `ui_checks/` | Playwright UI 截图 |
| `traces/` | LLM 调用追踪日志 |

`.opclog/` 会自动添加到目标项目的 `.gitignore`。

---

## 环境变量

| 变量 | 说明 |
|---|---|
| `OPENAI_API_KEY` | API 密钥 |
| `OPENAI_API_BASE` | API 基础 URL（兼容 OpenAI 格式）|
| `DEFAULT_LLM_MODEL` | 默认模型（litellm 格式）|
| `LLM_TIMEOUT` | LLM 调用超时（秒）|
| `OPC_FORMATTER` | 显式格式化命令（或 `none` 禁用）|
| `OPC_ENABLE_UI_CHECK` | 设为 `1` 启用 Playwright UI 验证 |
| `OPC_UI_URL` | 指定 UI 验证的 URL（跳过端口探测）|
| `BUILD_TIMEOUT` | 构建命令超时（秒，默认 120）|
| `UI_CHECK_TIMEOUT` | UI 验证超时（秒，默认 60）|

---

## 相关文档

- [`日志/step_plan.md`](日志/step_plan.md)：当前步骤进展
- [`日志/roadmap.md`](日志/roadmap.md)：后续路线图
- [`日志/version_evaluation.md`](日志/version_evaluation.md)：版本评价
- [`../../docs/workflow.md`](../../docs/workflow.md)：总体自动化工作流
- [`../../docs/workflow_local_optimize.md`](../../docs/workflow_local_optimize.md)：本地优化工作流细节
