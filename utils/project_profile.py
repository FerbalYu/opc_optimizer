"""Smart Project Profile detection and caching (v2.10.0 — Step 14).

Detects the project's tech stack using a hybrid approach:
  1. Rule-table quick-match (fast, free)
  2. LLM fallback for unknown project types (~500 tokens)

The result is cached to `.opclog/.project_profile.json` and reused
until the root-level file listing changes (hash-based invalidation).
"""

import os
import json
import hashlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("opc.project_profile")

__all__ = [
    "detect_project_profile",
    "load_project_profile",
    "invalidate_profile_cache",
]

# ─── Extended Rule Table ────────────────────────────────────────
# Each entry maps a project type to its detection markers, extensions,
# build/test commands, and optimization hints.

PROFILE_RULES: Dict[str, Dict[str, Any]] = {
    "python": {
        "markers": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"],
        "scan_extensions": [".py", ".pyi"],
        "test_cmd": "pytest",
        "build_cmd": None,
        "dev_cmd": None,
        "formatter": "ruff format",
        "ignore_dirs": ["venv", ".venv", "__pycache__", "dist", ".eggs", "*.egg-info"],
        "optimization_hints": [
            "使用 __slots__ 减少内存开销",
            "避免全局变量查找，用局部引用替代",
            "用 list/dict/set comprehension 替代手动循环",
            "io 密集场景使用 asyncio 或线程池",
        ],
    },
    "javascript": {
        "markers": ["package.json"],
        "scan_extensions": [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"],
        "test_cmd": "npm test",
        "build_cmd": "npm run build",
        "dev_cmd": "npm run dev",
        "formatter": "prettier --write",
        "ignore_dirs": ["node_modules", "dist", "build", ".next", ".nuxt"],
        "optimization_hints": [
            "减少 bundle 体积: tree-shaking + 动态 import",
            "避免在循环中创建闭包",
            "使用 const 代替 let（如无重赋值）",
        ],
    },
    "go": {
        "markers": ["go.mod"],
        "scan_extensions": [".go"],
        "test_cmd": "go test ./...",
        "build_cmd": "go build ./...",
        "dev_cmd": None,
        "formatter": "gofmt -w",
        "ignore_dirs": ["vendor"],
        "optimization_hints": [
            "使用 sync.Pool 复用对象减少 GC 压力",
            "避免不必要的 interface{} 类型断言",
            "goroutine 泄漏检查: 确保每个 goroutine 有退出路径",
        ],
    },
    "rust": {
        "markers": ["Cargo.toml"],
        "scan_extensions": [".rs"],
        "test_cmd": "cargo test",
        "build_cmd": "cargo build",
        "dev_cmd": None,
        "formatter": "rustfmt",
        "ignore_dirs": ["target"],
        "optimization_hints": [
            "使用 &str 代替 String clone",
            "考虑用 Vec::with_capacity 预分配",
            "避免不必要的 Arc/Mutex，优先用所有权转移",
        ],
    },
    "java": {
        "markers": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "scan_extensions": [".java", ".kt"],
        "test_cmd": None,
        "build_cmd": None,
        "dev_cmd": None,
        "formatter": None,
        "ignore_dirs": ["target", "build", ".gradle", ".idea"],
        "optimization_hints": [
            "使用 StringBuilder 代替字符串拼接",
            "集合初始化时预估容量",
            "减少自动装箱/拆箱",
        ],
    },
    "csharp": {
        "markers": ["*.csproj", "*.sln"],
        "scan_extensions": [".cs"],
        "test_cmd": "dotnet test",
        "build_cmd": "dotnet build",
        "dev_cmd": None,
        "formatter": "dotnet format",
        "ignore_dirs": ["bin", "obj", ".vs"],
        "optimization_hints": [
            "使用 Span<T> / Memory<T> 替代数组复制",
            "async 方法避免 .Result 和 .Wait() 死锁",
        ],
    },
    "flutter": {
        "markers": ["pubspec.yaml"],
        "scan_extensions": [".dart"],
        "test_cmd": "flutter test",
        "build_cmd": "flutter build",
        "dev_cmd": "flutter run -d chrome",
        "formatter": "dart format",
        "ignore_dirs": [".dart_tool", "build", ".flutter-plugins"],
        "optimization_hints": [
            "使用 const 构造函数避免不必要的 rebuild",
            "ListView.builder 代替 ListView(children: [...])",
            "拆分大 Widget 提高 rebuild 粒度",
        ],
    },
    "微信小程序": {
        "markers": ["app.json"],
        "extra_check": lambda path: os.path.exists(os.path.join(path, "app.wxss"))
                                    or os.path.exists(os.path.join(path, "app.js")),
        "scan_extensions": [".js", ".wxml", ".wxss", ".wxs", ".json"],
        "test_cmd": None,
        "build_cmd": None,
        "dev_cmd": None,
        "formatter": "prettier --parser babel",
        "ignore_dirs": ["miniprogram_npm", "node_modules"],
        "optimization_hints": [
            "setData 调用要合并，避免频繁触发视图层更新",
            "小程序包大小 2MB 限制，注意代码体积",
            "使用 wx:key 优化列表渲染性能",
        ],
    },
    "vue": {
        "markers": ["package.json"],
        "extra_check": lambda path: (
            os.path.exists(os.path.join(path, "vue.config.js"))
            or any(
                os.path.exists(os.path.join(path, f))
                for f in ["vite.config.ts", "vite.config.js", "vite.config.mts"]
            )
            or _package_json_has(path, "vue")
        ),
        "scan_extensions": [".vue", ".js", ".ts", ".jsx", ".tsx"],
        "test_cmd": "npm test",
        "build_cmd": "npm run build",
        "dev_cmd": "npm run dev",
        "formatter": "prettier --write",
        "ignore_dirs": ["node_modules", "dist", ".nuxt"],
        "optimization_hints": [
            "computed 代替 watch 做派生状态",
            "v-show vs v-if: 频繁切换用 v-show",
            "大列表使用虚拟滚动 (virtual-scroller)",
            "组件懒加载: defineAsyncComponent",
        ],
    },
    "react": {
        "markers": ["package.json"],
        "extra_check": lambda path: _package_json_has(path, "react"),
        "scan_extensions": [".jsx", ".tsx", ".js", ".ts"],
        "test_cmd": "npm test",
        "build_cmd": "npm run build",
        "dev_cmd": "npm run dev",
        "formatter": "prettier --write",
        "ignore_dirs": ["node_modules", "dist", "build", ".next"],
        "optimization_hints": [
            "React.memo + useMemo 避免不必要的重复渲染",
            "useCallback 稳定回调引用",
            "大列表使用 react-window / react-virtuoso",
        ],
    },
    "ruby": {
        "markers": ["Gemfile", "Rakefile"],
        "scan_extensions": [".rb", ".erb", ".rake"],
        "test_cmd": "bundle exec rspec",
        "build_cmd": None,
        "dev_cmd": None,
        "formatter": "rubocop -A",
        "ignore_dirs": ["vendor", "tmp", "log"],
        "optimization_hints": [
            "使用 freeze 冻结字符串常量",
            "N+1 查询检查: 使用 includes/eager_load",
        ],
    },
}


# ─── Helper Functions ───────────────────────────────────────────

def _package_json_has(project_path: str, dep_keyword: str) -> bool:
    """Check if package.json contains a dependency matching keyword."""
    pkg_path = os.path.join(project_path, "package.json")
    if not os.path.exists(pkg_path):
        return False
    try:
        with open(pkg_path, "r", encoding="utf-8") as f:
            content = f.read(8192)  # Read first 8KB only
        return dep_keyword in content
    except (OSError, UnicodeDecodeError):
        return False


def _compute_root_hash(project_path: str) -> str:
    """Compute a hash of root-level filenames for cache invalidation."""
    try:
        entries = sorted(os.listdir(project_path))
    except OSError:
        entries = []
    return hashlib.md5("|".join(entries).encode()).hexdigest()


def _generate_dir_tree(project_path: str, max_depth: int = 3) -> str:
    """Generate a compact directory tree string for LLM context."""
    skip = {".git", "node_modules", "venv", ".venv", "__pycache__",
            "dist", "build", "target", ".opclog", ".idea", ".vs"}
    lines = []

    def _walk(path: str, prefix: str, depth: int):
        if depth > max_depth:
            return
        try:
            entries = sorted(os.listdir(path))
        except OSError:
            return
        dirs = [e for e in entries if os.path.isdir(os.path.join(path, e)) and e not in skip]
        files = [e for e in entries if os.path.isfile(os.path.join(path, e))]

        for f in files:
            lines.append(f"{prefix}{f}")
        for d in dirs:
            lines.append(f"{prefix}{d}/")
            _walk(os.path.join(path, d), prefix + "  ", depth + 1)

    _walk(project_path, "", 0)
    return "\n".join(lines[:200])  # Cap at 200 lines


def _collect_clue_files(project_path: str) -> str:
    """Collect the first ~20 lines of key project files as clues for LLM."""
    clue_files = [
        "README.md", "README.rst", "README.txt", "README",
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        "Makefile", "CMakeLists.txt",
        "pyproject.toml", "setup.py", "setup.cfg",
        "package.json", "tsconfig.json",
        "go.mod", "Cargo.toml", "pubspec.yaml",
        "Gemfile", "build.gradle", "pom.xml",
        "app.json",  # 微信小程序
    ]
    snippets = []
    for name in clue_files:
        fp = os.path.join(project_path, name)
        if os.path.isfile(fp):
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    head = "".join(f.readline() for _ in range(20))
                snippets.append(f"--- {name} ---\n{head.strip()}")
            except OSError:
                continue
    return "\n\n".join(snippets)


# ─── Core Detection ─────────────────────────────────────────────

def _match_rules(project_path: str) -> Optional[Dict[str, Any]]:
    """Try rule-table matching. Returns profile dict or None."""
    # Priority order: more specific types first (vue/react before generic js)
    priority = [
        "微信小程序", "flutter", "vue", "react",
        "python", "go", "rust", "java", "csharp", "ruby",
        "javascript",  # generic JS last
    ]

    for ptype in priority:
        rule = PROFILE_RULES.get(ptype)
        if not rule:
            continue

        # Check markers
        marker_hit = False
        for marker in rule["markers"]:
            if "*" in marker:
                import glob
                if glob.glob(os.path.join(project_path, marker)):
                    marker_hit = True
                    break
            else:
                if os.path.exists(os.path.join(project_path, marker)):
                    marker_hit = True
                    break

        if not marker_hit:
            continue

        # Check extra_check if present (e.g., vue needs vite.config or vue dep)
        extra = rule.get("extra_check")
        if extra and not extra(project_path):
            continue

        # Match found
        profile = {
            "type": ptype,
            "languages": _infer_languages(ptype),
            "scan_extensions": rule["scan_extensions"],
            "test_cmd": rule.get("test_cmd"),
            "build_cmd": rule.get("build_cmd"),
            "dev_cmd": rule.get("dev_cmd"),
            "formatter": rule.get("formatter"),
            "ignore_dirs": rule.get("ignore_dirs", []),
            "optimization_hints": rule.get("optimization_hints", []),
            "detected_by": "rules",
        }
        logger.info(f"Rule-table match: {ptype}")
        return profile

    return None


def _infer_languages(ptype: str) -> List[str]:
    """Infer programming languages from project type."""
    lang_map = {
        "python": ["python"],
        "javascript": ["javascript", "typescript"],
        "go": ["go"],
        "rust": ["rust"],
        "java": ["java", "kotlin"],
        "csharp": ["csharp"],
        "flutter": ["dart"],
        "微信小程序": ["javascript", "wxml", "wxss"],
        "vue": ["javascript", "typescript", "vue"],
        "react": ["javascript", "typescript", "jsx", "tsx"],
        "ruby": ["ruby"],
    }
    return lang_map.get(ptype, [ptype])


def _llm_detect(project_path: str, llm=None) -> Dict[str, Any]:
    """Use LLM to detect project type when rules don't match."""
    if llm is None:
        # Return a generic fallback profile if no LLM available
        logger.warning("No LLM available for project detection, using generic profile")
        return _generic_profile()

    dir_tree = _generate_dir_tree(project_path)
    clues = _collect_clue_files(project_path)

    prompt = f"""Analyze this project and determine its type and tech stack.

Directory tree:
{dir_tree}

Key file snippets:
{clues}

Return a JSON object with:
{{
  "type": "<project type, e.g. python, vue, flutter, 微信小程序, etc.>",
  "languages": ["<primary language>", ...],
  "scan_extensions": [".ext1", ".ext2"],
  "test_cmd": "<test command or null>",
  "build_cmd": "<build command or null>",
  "dev_cmd": "<dev server command or null>",
  "formatter": "<formatter command or null>",
  "ignore_dirs": ["dir1", "dir2"],
  "optimization_hints": ["hint1", "hint2", "hint3"]
}}

IMPORTANT:
- optimization_hints should be 2-4 specific, actionable tips for THIS project type
- scan_extensions should include ALL relevant source file extensions
- Use null (not "null") for commands that don't apply
"""

    try:
        result = llm.generate_json([
            {"role": "system", "content": "You are a project type detector. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ])
        result["detected_by"] = "llm"
        # Ensure all required fields exist
        for key in ["type", "languages", "scan_extensions", "optimization_hints"]:
            if key not in result:
                result[key] = [] if key != "type" else "unknown"
        for key in ["test_cmd", "build_cmd", "formatter"]:
            if key not in result:
                result[key] = None
        if "dev_cmd" not in result:
            result["dev_cmd"] = None
        if "ignore_dirs" not in result:
            result["ignore_dirs"] = []
        logger.info(f"LLM detected project type: {result.get('type', 'unknown')}")
        return result
    except Exception as e:
        logger.error(f"LLM project detection failed: {e}")
        return _generic_profile()


def _generic_profile() -> Dict[str, Any]:
    """Return a generic fallback profile."""
    return {
        "type": "unknown",
        "languages": [],
        "scan_extensions": [".py", ".js", ".ts", ".java", ".go", ".rs", ".md"],
        "test_cmd": None,
        "build_cmd": None,
        "dev_cmd": None,
        "formatter": None,
        "ignore_dirs": [],
        "optimization_hints": [],
        "detected_by": "fallback",
    }


# ─── Public API ─────────────────────────────────────────────────

def detect_project_profile(project_path: str, llm=None) -> Dict[str, Any]:
    """Detect the project profile using rules + optional LLM fallback.

    Args:
        project_path: Absolute path to the project directory.
        llm: Optional LLMService instance for fallback detection.

    Returns:
        A dict containing: type, languages, scan_extensions, test_cmd,
        build_cmd, formatter, ignore_dirs, optimization_hints, detected_by.
    """
    if not os.path.isdir(project_path):
        logger.warning(f"Project path does not exist: {project_path}")
        return _generic_profile()

    # Step 1: Try rule-table match
    profile = _match_rules(project_path)
    if profile:
        return profile

    # Step 2: LLM fallback
    logger.info("No rule-table match, attempting LLM detection...")
    return _llm_detect(project_path, llm)


def load_project_profile(project_path: str, llm=None) -> Dict[str, Any]:
    """Load project profile with caching.

    Checks `.opclog/.project_profile.json` first. If the cache is valid
    (exists and root hash matches), returns cached profile. Otherwise,
    detects fresh and writes cache.

    Args:
        project_path: Absolute path to the project directory.
        llm: Optional LLMService instance for LLM fallback.

    Returns:
        Project profile dict.
    """
    # Use external workspace for cache (Opt-6)
    try:
        from utils.workspace import workspace_path
        cache_path = workspace_path(project_path, "cache", "project_profile.json")
    except Exception:
        cache_path = os.path.join(project_path, ".opclog", ".project_profile.json")
    current_hash = _compute_root_hash(project_path)

    # Try cache
    if os.path.isfile(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("_root_hash") == current_hash:
                logger.info(f"Using cached profile: {cached.get('type', 'unknown')}")
                return cached
            else:
                logger.info("Root hash changed, re-detecting project profile...")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Cache read failed: {e}")

    # Detect fresh
    profile = detect_project_profile(project_path, llm)
    profile["_root_hash"] = current_hash

    # Write cache
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            # Convert any non-serializable items (like lambdas) — shouldn't be in profile
            json.dump(profile, f, indent=2, ensure_ascii=False)
        logger.info(f"Profile cached to {cache_path}")
    except OSError as e:
        logger.warning(f"Failed to write profile cache: {e}")

    return profile


def invalidate_profile_cache(project_path: str) -> bool:
    """Delete the cached project profile.

    Args:
        project_path: Absolute path to the project directory.

    Returns:
        True if cache was deleted, False if it didn't exist.
    """
    # Use external workspace for cache (Opt-6)
    try:
        from utils.workspace import workspace_path
        cache_path = workspace_path(project_path, "cache", "project_profile.json")
    except Exception:
        cache_path = os.path.join(project_path, ".opclog", ".project_profile.json")
    if os.path.isfile(cache_path):
        os.remove(cache_path)
        logger.info("Profile cache invalidated")
        return True
    return False
