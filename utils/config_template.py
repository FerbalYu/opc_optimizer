"""Project type detection and config template generation (v2.9.0).

Detects the project's tech stack and generates a commented opc.config.yaml
template with sensible defaults for that stack.
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("opc.config_template")

# ─── Project type detection ─────────────────────────────────────

PROJECT_TYPES = {
    "python": {
        "markers": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"],
        "extensions": [".py"],
        "icon": "🐍",
        "formatters": ["ruff format", "black"],
    },
    "javascript": {
        "markers": ["package.json", "tsconfig.json", ".eslintrc.js", ".eslintrc.json"],
        "extensions": [".js", ".jsx", ".ts", ".tsx"],
        "icon": "📦",
        "formatters": ["prettier --write"],
    },
    "go": {
        "markers": ["go.mod", "go.sum"],
        "extensions": [".go"],
        "icon": "🐹",
        "formatters": ["gofmt -w"],
    },
    "rust": {
        "markers": ["Cargo.toml", "Cargo.lock"],
        "extensions": [".rs"],
        "icon": "🦀",
        "formatters": ["rustfmt"],
    },
    "java": {
        "markers": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "extensions": [".java", ".kt"],
        "icon": "☕",
        "formatters": [],
    },
    "csharp": {
        "markers": ["*.csproj", "*.sln"],
        "extensions": [".cs"],
        "icon": "🔷",
        "formatters": ["dotnet format"],
    },
}


def detect_project_type(project_path: str) -> Dict[str, Any]:
    """Detect the project's tech stack.

    Returns:
        {
            "types": ["python", "javascript"],  # detected types
            "primary": "python",                 # most likely primary type
            "file_count": 42,                    # total code files
            "details": {
                "python": {"files": 30, "icon": "🐍", "formatters": [...]},
                "javascript": {"files": 12, "icon": "📦", "formatters": [...]},
            }
        }
    """
    if not os.path.isdir(project_path):
        return {"types": [], "primary": None, "file_count": 0, "details": {}, "valid": False}

    detected = {}
    total_files = 0

    # Check markers
    for ptype, info in PROJECT_TYPES.items():
        for marker in info["markers"]:
            if "*" in marker:
                # Glob pattern — check for any matching file
                import glob
                if glob.glob(os.path.join(project_path, marker)):
                    detected.setdefault(ptype, {"files": 0, "icon": info["icon"], "formatters": info["formatters"]})
            else:
                if os.path.exists(os.path.join(project_path, marker)):
                    detected.setdefault(ptype, {"files": 0, "icon": info["icon"], "formatters": info["formatters"]})

    # Count files by extension
    skip_dirs = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", "target", ".opclog"}
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            for ptype, info in PROJECT_TYPES.items():
                if ext in info["extensions"]:
                    detected.setdefault(ptype, {"files": 0, "icon": info["icon"], "formatters": info["formatters"]})
                    detected[ptype]["files"] += 1
                    total_files += 1

    # Determine primary type (most files)
    types = sorted(detected.keys(), key=lambda t: detected[t]["files"], reverse=True)
    primary = types[0] if types else None

    return {
        "types": types,
        "primary": primary,
        "file_count": total_files,
        "details": detected,
        "valid": True,
    }


def validate_project_path(path: str) -> Dict[str, Any]:
    """Validate a project path and return rich info.

    Returns:
        {
            "valid": bool,
            "exists": bool,
            "type_info": {...},  # from detect_project_type
            "message": str,     # human-readable status
        }
    """
    if not path or not path.strip():
        return {"valid": False, "exists": False, "type_info": {}, "message": "路径不能为空"}

    path = path.strip()
    exists = os.path.isdir(path)
    if not exists:
        return {"valid": False, "exists": False, "type_info": {}, "message": f"目录不存在: {path}"}

    type_info = detect_project_type(path)
    if type_info["file_count"] == 0:
        return {
            "valid": False, "exists": True, "type_info": type_info,
            "message": "⚠️ 未检测到代码文件",
        }

    # Build message
    type_tags = " ".join(
        f"{type_info['details'][t]['icon']} {t.title()} ({type_info['details'][t]['files']})"
        for t in type_info["types"]
    )
    return {
        "valid": True, "exists": True, "type_info": type_info,
        "message": f"✅ {type_info['file_count']} 个代码文件 | {type_tags}",
    }


# ─── Config template generation ─────────────────────────────────

TEMPLATE_HEADER = """# OPC Optimizer 配置文件
# 优先级: CLI 参数 > opc.config.yaml > ~/.opc/config.yaml > 默认值
# 将此文件放在项目根目录即可生效
"""


def generate_template(project_path: str = "") -> str:
    """Generate a commented opc.config.yaml template.

    If project_path is provided, auto-fills with detected project info.
    """
    lines = [TEMPLATE_HEADER]

    # Detect project info for smart defaults
    formatter_hint = "# formatter: \"ruff format\"  # 或 black, prettier 等"
    type_comment = ""

    if project_path and os.path.isdir(project_path):
        info = detect_project_type(project_path)
        if info["primary"]:
            type_comment = f"# 检测到项目类型: {info['primary'].title()}"
            fmts = info["details"].get(info["primary"], {}).get("formatters", [])
            if fmts:
                formatter_hint = f'formatter: "{fmts[0]}"  # 自动检测推荐'

    lines.append(f"""
{type_comment}

# ─── 基础配置 ───────────────────────────────────────
goal: "Improve code quality, performance, and architecture"
max_rounds: 5
archive_every: 3

# ─── 运行模式 ───────────────────────────────────────
# dry_run: true       # 仅预览，不修改文件
# auto: true          # 无人值守模式

# ─── LLM 配置 ───────────────────────────────────────
# model: "openai/gpt-4o"        # 默认模型
# plan_model: "openai/gpt-4o"   # 规划节点模型
# execute_model: "openai/gpt-4o" # 执行节点模型
# test_model: "openai/gpt-4o-mini" # 测试节点模型 (可用小模型)
timeout: 120                     # LLM 调用超时 (秒)

# ─── 格式化 (v2.8.0) ────────────────────────────────
{formatter_hint}
# 设为 "none" 禁用自动格式化

# ─── 文件过滤 ───────────────────────────────────────
# max_file_size: 512000   # 单文件最大字节数
# allowed_extensions:
#   - .py
#   - .js
#   - .ts
#   - .go
#   - .rs

# ─── 安全 ───────────────────────────────────────────
# build_timeout: 120      # 构建/测试命令超时 (秒)
""")

    return "\n".join(lines)
