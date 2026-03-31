---
keywords: []
always: true
---
# Clean Code Principles (All Projects)

## 函数设计
- 单一职责：每个函数只做一件事
- 函数体不超过 30 行（超过则拆分）
- 参数不超过 4 个（超过则用对象/结构体封装）
- 避免布尔参数（拆成两个语义清晰的函数）

## 命名
- 变量名 = 名词 / 形容词（`user_count`, `is_valid`）
- 函数名 = 动词开头（`get_user`, `validate_input`, `calculate_total`）
- 常量全大写 + 下划线（`MAX_RETRIES`, `DEFAULT_TIMEOUT`）
- 避免缩写和单字母变量（循环变量 `i`、lambda 参数除外）

## 代码结构
- DRY：重复代码超过 2 次就抽取为共享函数
- 早返回（Guard Clause）替代深层嵌套 if-else
- Magic Number 用命名常量替代
- 相关逻辑分组，不相关的代码用空行分隔

## 错误处理
- 不要 catch 后静默吞掉错误（至少记日志）
- 异常信息要有上下文（what happened + where + relevant data）
- 区分可恢复错误（重试）和不可恢复错误（快速失败）

## 注释与文档
- 注释说 WHY 不说 WHAT（代码本身说 WHAT）
- 公开 API 都要有文档字符串
- 过时的注释比没注释更有害 — 代码变了注释也要更新
