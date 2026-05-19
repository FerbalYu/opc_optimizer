"""Prompt language policy for OPC.

Machine-readable protocols stay in English, while user-visible artifacts should
default to Simplified Chinese.
"""

USER_VISIBLE_LANGUAGE_DIRECTIVE = """
## 输出语言要求
- 面向用户阅读的内容必须使用简体中文，包括计划说明、现状评估、产品经理摘要、风险说明、验收说明、优化建议和报告文字。
- 保留机器协议为英文：JSON 字段名、SEARCH/REPLACE 标记、NO_CHANGES、文件路径、命令、代码标识符和异常原文不要翻译。
- 如果用户目标包含中文约束，必须原样保留其含义，尤其是“测试文件不变”“保持函数名不变”“不要改接口”等边界。
- 不要把中文目标先改写成更弱的英文目标；可以补充技术术语，但不能丢失原始约束。
"""


def user_visible_language_directive() -> str:
    """Return the shared language directive injected into LLM prompts."""
    return USER_VISIBLE_LANGUAGE_DIRECTIVE.strip()
