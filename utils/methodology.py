"""Optimization methodology — principles injected into every LLM prompt (v2.2.0).

This module encodes the working discipline of the optimizer so that any
LLM (strong or weak) follows a structured, careful approach when
modifying code.
"""

# ── System-level methodology injected into every planning prompt ─────

PLAN_METHODOLOGY = """
## 方法论 — 必须遵守

### 原则
1. **先读后写**：必须基于上方真实代码制定计划，不要规划没看过的代码。
2. **最小侵入**：只改优化目标真正需要的内容，不做无关重构。
3. **自底向上**：按依赖顺序规划：工具/辅助函数 → 业务逻辑 → 入口 → UI。
4. **一次一件事**：每个改动项只解决一个问题，不要把“加类型标注”和“重构循环”混在一个任务里。
5. **保持行为**：不能破坏既有功能；如果不确定，必须明确标注风险。

### 计划格式
- 按文件分组，而不是按主题分组。
- 每个改动都要说明具体函数、类或位置。
- 说明为什么改，而不仅是改什么。
- 风险用 low / medium / high 表示。
- 一个改动失败时，其余改动仍应独立有效。
"""

# ── System-level methodology injected into every execution prompt ────

EXECUTE_METHODOLOGY = """
## 方法论 — 必须遵守

### 代码修改规则
1. **精确匹配**：`old_content_snippet` 必须是当前文件中的逐字符精确子串。
2. **最小 diff**：只替换必要的最小片段；改一行时不要重写整个函数。
3. **无副作用**：改动不能影响目标函数或代码块之外的行为。
4. **风格一致**：缩进、命名、引号等必须匹配当前文件风格。
5. **依赖感知**：新增 import 要放在现有 import 区域；重命名函数时必须考虑调用点。

### 安全检查
- 不要新增 `eval()`、`exec()`、`os.system()`、`subprocess.call(..., shell=True)`。
- 不要删除错误处理，除非同时提供等价替代。
- 不要删除备份、日志或安全保护代码。
- 不要引入循环导入。

### 质量要求
- 不为小修小补强行添加无关 docstring。
- 变量名应清晰，列表推导式等局部场景可使用短变量。
- 不新增难以解释的 magic number。
"""

# ── System-level methodology injected into review/test prompt ────────

REVIEW_METHODOLOGY = """
## 评审方法论 — 必须遵守

### 评审清单
1. **正确性**：改动是否完成计划目标，边界情况是否覆盖。
2. **安全性**：是否存在 eval、shell 注入、路径穿越等危险模式。
3. **回归风险**：是否可能破坏既有行为，是否检查了调用点。
4. **风格一致性**：是否符合当前代码库风格。
5. **完整性**：必要改动是否齐全，是否缺 import 或调用点更新。

### 评分
- 每个改动按 PASS / WARN / FAIL 标记。
- FAIL：下一轮前必须回滚或修复。
- WARN：可接受，但后续应优化。
- PASS：质量良好，无明显问题。
"""
