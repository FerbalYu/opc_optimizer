# P0-1 基线数据采集报告

## 1. 采集范围

- 采集时间：2026-04-07
- 工作目录：`d:\workflow\opc\src\opc_optimizer`
- Python 版本：`3.14.0`
- pytest 版本：`9.0.2`
- 目标：建立当前环境下的测试通过率、关键耗时、样本输入输出基线。

## 2. 测试通过率基线

采集命令（来自 `task.md` 的 P0-1 验证记录）：

1. `python -m pytest -q`
2. `python -m pytest tests/test_graph.py -q`
3. `python -m pytest tests/test_nodes_integration.py -q`

结果统计：

- 总命令数：`3`
- 通过：`0`
- 失败：`3`
- 命令通过率：`0.00%`

## 3. 关键耗时基线

- `python -m pytest -q`
  - 耗时：`0.44s`
  - 结果：失败（收集阶段 4 个错误）
- `python -m pytest tests/test_graph.py -q`
  - 耗时：`0.13s`
  - 结果：失败（收集阶段导入错误）
- `python -m pytest tests/test_nodes_integration.py -q`
  - 耗时：`0.81s`
  - 结果：失败（11 个失败用例）

说明：当前耗时反映的是“快速失败耗时”，不是“完整测试执行耗时”。

## 4. 失败基线（摘要）

### 4.1 全量测试收集失败（`pytest -q`）

- `ModuleNotFoundError: No module named 'local_optimizer'`
- `ModuleNotFoundError: No module named 'langgraph'`
- `ImportError: attempted relative import with no known parent package`

### 4.2 图相关测试失败（`tests/test_graph.py`）

- `ModuleNotFoundError: No module named 'langgraph'`

### 4.3 节点集成测试失败（`tests/test_nodes_integration.py`）

- `AttributeError: module 'nodes' has no attribute 'plan' / 'test'`
- `ModuleNotFoundError: No module named 'litellm'`

## 5. 样本输入/输出（2 组）

### 样本 A：CLI 帮助信息（成功路径）

- 输入：`python -m cli --help`
- 输出（摘要）：
  - `usage: python.exe -m cli [-h] {test,format,lint,security-check,audit} ...`
  - 展示了 `test/format/lint/security-check/audit` 子命令
- 判定：命令可执行，CLI 入口可用。

### 样本 B：安全检查命令（失败路径）

- 输入：`python -m cli security-check`
- 输出（摘要）：
  - `Could not find pyproject.toml`
  - 提示需要有效项目根目录或设置 `OPC_PROJECT_ROOT`
- 判定：工具链可运行，但当前目录结构与 `find_project_root()` 预期不一致。

## 6. 当前风险

- 环境依赖不完整：缺 `langgraph`、`litellm`。
- 包路径命名不一致：`opc_optimizer` 与 `local_optimizer` 混用迹象明显。
- 入口运行路径依赖较强：`pyproject.toml` 发现机制对目录结构敏感。

## 7. 下一步建议（P0-2/P0-3 前置）

1. 先补齐缺失依赖（至少 `langgraph`、`litellm`）并固定可复现安装方式。  
2. 统一包名/导入路径策略（`opc_optimizer` vs `local_optimizer`）。  
3. 明确测试运行工作目录规范，必要时在文档中强制指定。  
4. 之后再进入 P0-2（模式标识）与 P0-3（观测字段）实现。
