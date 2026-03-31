"""Context7 documentation grounding helpers (Step 17).

This module provides an optional bridge from OPC's execute phase to a
Context7-compatible MCP server via the OpenAI Responses API.

Design goals:
1. Best-effort only: failures must never block optimization.
2. Low coupling: callers can inject a fake client in tests.
3. Runtime-safe: the feature is disabled unless explicitly configured.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger("opc.context7")

__all__ = [
    "is_context7_enabled",
    "guess_libraries",
    "query_docs",
    "collect_relevant_docs",
]


PROFILE_LIBRARY_HINTS: Dict[str, List[str]] = {
    "vue": ["vue"],
    "react": ["react"],
    "flutter": ["flutter"],
    "javascript": ["node.js"],
    "python": ["python"],
    "wechat_miniprogram": ["wechat miniprogram"],
}

PLAN_KEYWORD_HINTS: Dict[str, str] = {
    "vue": "vue",
    "react": "react",
    "next.js": "next.js",
    "nextjs": "next.js",
    "nuxt": "nuxt",
    "vite": "vite",
    "fastapi": "fastapi",
    "django": "django",
    "flask": "flask",
    "pydantic": "pydantic",
    "langgraph": "langgraph",
    "litellm": "litellm",
    "playwright": "playwright",
}


def _normalize_profile_type(profile_type: str) -> str:
    text = (profile_type or "").strip().lower()
    if "微信" in text or "miniprogram" in text:
        return "wechat_miniprogram"
    return text.replace(" ", "_")


def _strip_provider_prefix(model_name: str) -> str:
    if "/" in model_name:
        return model_name.split("/")[-1]
    return model_name


def _read_json(path: str) -> Dict[str, object]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _guess_from_package_json(project_path: str) -> List[str]:
    package_json = _read_json(os.path.join(project_path, "package.json"))
    if not package_json:
        return []

    merged: Dict[str, object] = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        value = package_json.get(key)
        if isinstance(value, dict):
            merged.update(value)

    known = [
        "vue",
        "react",
        "next",
        "nuxt",
        "vite",
        "@angular/core",
        "svelte",
        "lit",
    ]
    results: List[str] = []
    for dep in known:
        if dep in merged:
            results.append("next.js" if dep == "next" else dep.replace("@angular/core", "angular"))
    return results


def _guess_from_python_files(project_path: str) -> List[str]:
    for name in ("requirements.txt", "pyproject.toml", "setup.py"):
        fp = os.path.join(project_path, name)
        if not os.path.isfile(fp):
            continue
        try:
            content = open(fp, "r", encoding="utf-8", errors="replace").read(16384).lower()
        except OSError:
            continue
        results: List[str] = []
        for dep in ("fastapi", "django", "flask", "pydantic", "langgraph", "litellm"):
            if dep in content:
                results.append(dep)
        if results:
            return results
    return []


def guess_libraries(project_path: str, plan: str, profile: Optional[Dict[str, object]] = None) -> List[str]:
    """Infer the most relevant library/framework names for docs grounding."""
    profile = profile or {}
    candidates: List[str] = []

    ptype = _normalize_profile_type(str(profile.get("type", "")))
    candidates.extend(PROFILE_LIBRARY_HINTS.get(ptype, []))

    candidates.extend(_guess_from_package_json(project_path))
    candidates.extend(_guess_from_python_files(project_path))

    lowered_plan = (plan or "").lower()
    for keyword, library in PLAN_KEYWORD_HINTS.items():
        if keyword in lowered_plan:
            candidates.append(library)

    deduped: List[str] = []
    seen = set()
    for item in candidates:
        normalized = item.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(item)
    return deduped[:3]


def is_context7_enabled() -> bool:
    """Return True only when runtime configuration is present."""
    flag = os.getenv("OPC_ENABLE_CONTEXT7", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return False
    return bool(os.getenv("CONTEXT7_SERVER_URL")) and bool(os.getenv("OPENAI_API_KEY"))


def query_docs(
    library: str,
    query: str,
    *,
    client: object | None = None,
    timeout: int = 45,
) -> str:
    """Query Context7 and return a concise markdown summary.

    If `client` exposes a `query_docs(library, query)` method, that is used directly.
    Otherwise this function attempts an OpenAI Responses API request against a remote
    MCP server configured via environment variables.
    """
    if client is not None and hasattr(client, "query_docs"):
        try:
            result = client.query_docs(library, query)
            return str(result).strip()
        except Exception as e:
            logger.warning(f"Injected Context7 client failed for {library}: {e}")
            return ""

    if not is_context7_enabled():
        return ""

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("OpenAI SDK not installed; Context7 disabled")
        return ""

    try:
        model_name = _strip_provider_prefix(
            os.getenv("CONTEXT7_MODEL") or os.getenv("DEFAULT_LLM_MODEL") or "gpt-4.1-mini"
        )
        headers = None
        headers_json = os.getenv("CONTEXT7_HEADERS_JSON", "").strip()
        if headers_json:
            parsed_headers = json.loads(headers_json)
            if isinstance(parsed_headers, dict):
                headers = {str(k): str(v) for k, v in parsed_headers.items()}

        openai_client = OpenAI(timeout=timeout)
        response = openai_client.responses.create(
            model=model_name,
            input=(
                f"Use the Context7 MCP server to resolve the correct library for '{library}' "
                f"and retrieve relevant official documentation for this task:\n\n{query}\n\n"
                "Return concise markdown with:\n"
                "1. Resolved library/package\n"
                "2. Relevant APIs or patterns\n"
                "3. Constraints to avoid outdated/wrong usage\n"
                "Keep it under 220 words."
            ),
            tools=[
                {
                    "type": "mcp",
                    "server_label": "context7",
                    "server_url": os.getenv("CONTEXT7_SERVER_URL"),
                    "headers": headers,
                    "require_approval": "never",
                }
            ],
            temperature=0,
        )
        return response.output_text.strip()
    except Exception as e:
        logger.warning(f"Context7 query failed for {library}: {e}")
        return ""


def collect_relevant_docs(
    project_path: str,
    plan: str,
    *,
    profile: Optional[Dict[str, object]] = None,
    client: object | None = None,
    max_docs: int = 2,
    max_chars: int = 4000,
) -> str:
    """Collect doc grounding for the most relevant libraries in the current plan."""
    libraries = guess_libraries(project_path, plan, profile=profile)
    if not libraries:
        return ""

    sections: List[str] = []
    for library in libraries[:max_docs]:
        summary = query_docs(
            library,
            query=plan[:2500],
            client=client,
        )
        if summary:
            sections.append(f"### {library}\n{summary}")

    if not sections:
        return ""

    combined = "## Relevant framework/library docs (Context7)\n\n" + "\n\n".join(sections)
    if len(combined) > max_chars:
        combined = combined[:max_chars].rsplit("\n", 1)[0]
        combined += "\n\n... (Context7 docs truncated due to token budget)"
    return combined
