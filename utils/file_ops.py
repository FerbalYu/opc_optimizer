import os
import time
import logging
from typing import List, Optional

logger = logging.getLogger("opc.file_ops")

__all__ = [
    "write_to_file", "append_to_file", "read_file",
    "get_project_files", "get_changed_files",
    "rank_files_by_complexity",
]

def write_to_file(file_path: str, content: str) -> None:
    """Safely write content to a file."""
    os.makedirs(os.path.dirname(os.path.abspath(file_path)) or '.', exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

def append_to_file(file_path: str, content: str) -> None:
    """Safely append content to a file."""
    os.makedirs(os.path.dirname(os.path.abspath(file_path)) or '.', exist_ok=True)
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(content)

def read_file(file_path: str, max_size: int = 512_000) -> str:
    """Safely read content from a file. Truncates if exceeds max_size bytes."""
    if not os.path.exists(file_path):
        return ""
    # Check size before reading
    file_size = os.path.getsize(file_path)
    with open(file_path, 'r', encoding='utf-8') as f:
        if file_size > max_size:
            content = f.read(max_size)
            return content + f"\n\n... [TRUNCATED: file is {file_size:,} bytes, showing first {max_size:,}]"
        return f.read()

def get_project_files(project_path: str, extensions: Optional[List[str]] = None,
                      profile: Optional[dict] = None) -> List[str]:
    """Get all relevant files in the project directory, respecting basic ignores.
    
    Args:
        project_path: Root directory to scan.
        extensions: File extensions to include. If None, uses profile's scan_extensions
                    or a default list.
        profile: Optional project profile dict (from project_profile.py). When provided,
                 uses its scan_extensions and ignore_dirs.
    """
    if extensions is None:
        if profile and profile.get("scan_extensions"):
            extensions = profile["scan_extensions"]
        else:
            extensions = ['.py', '.js', '.ts', '.java', '.go', '.md']
        
    default_ignore = {'.git', 'node_modules', 'venv', '__pycache__', 'dist', 'build', '.opclog'}
    if profile and profile.get("ignore_dirs"):
        ignore_dirs = default_ignore | set(profile["ignore_dirs"])
    else:
        ignore_dirs = default_ignore
    
    ignore_extensions = {
        '.env', '.bak', '.log', '.lock', '.pyc',
        '.svg', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.webp',
        '.woff', '.woff2', '.ttf', '.eot', '.otf',
        '.map', '.min.js', '.min.css', '.mp4', '.webm', '.pdf', '.zip', '.tar', '.gz'
    }
    
    files = []
    for root, dirs, filenames in os.walk(project_path):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        
        for filename in filenames:
            if any(filename.endswith(ext) for ext in ignore_extensions):
                continue
            if any(filename.endswith(ext) for ext in extensions):
                filepath = os.path.join(root, filename)
                # Skip massive files (e.g., > 500KB) to save token budget
                try:
                    if os.path.getsize(filepath) > 500_000:
                        continue
                except OSError:
                    continue
                files.append(filepath)
                
    # Cap total files scanned to prevent extreme context bloat
    if len(files) > 150:
        files = files[:150]
        
    return files


# ─── Incremental file scanning ──────────────────────────────────────

# Module-level cache for last scan timestamp
_last_scan_time: float = 0.0


def get_changed_files(
    project_path: str,
    extensions: Optional[List[str]] = None,
) -> List[str]:
    """Return only files modified since the last call (mtime-based).
    
    On the first call (or when _last_scan_time is 0), returns ALL project files.
    Subsequent calls return only files whose mtime is newer than the last scan.
    """
    global _last_scan_time
    
    all_files = get_project_files(project_path, extensions)
    
    if _last_scan_time == 0.0:
        # First call — return everything
        _last_scan_time = time.time()
        logger.info(f"Initial scan: {len(all_files)} files")
        return all_files
    
    cutoff = _last_scan_time
    changed = []
    for fp in all_files:
        try:
            if os.path.getmtime(fp) > cutoff:
                changed.append(fp)
        except OSError:
            continue
    
    _last_scan_time = time.time()
    logger.info(f"Incremental scan: {len(changed)} changed files (of {len(all_files)} total)")
    return changed if changed else all_files  # fallback to all if nothing changed


# ─── File complexity ranking (v2.2.0) ───────────────────────────────

# Basenames to skip when ranking (config/tool files)
_SKIP_BASENAMES = {
    "setup.py", "setup.cfg", "conftest.py", "__init__.py",
    "manage.py", "wsgi.py", "asgi.py",
}


def _file_complexity_score(filepath: str) -> float:
    """Calculate a complexity score for a file: line_count × avg_indent_depth.
    
    Uses average indentation as a rough proxy for cyclomatic complexity.
    Returns 0 on any read error.
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except OSError:
        return 0.0
    
    if not lines:
        return 0.0
    
    non_blank = [ln for ln in lines if ln.strip()]
    if not non_blank:
        return 0.0
    
    total_indent = sum(len(ln) - len(ln.lstrip()) for ln in non_blank)
    avg_indent = total_indent / len(non_blank)
    
    return len(non_blank) * max(avg_indent, 1.0)


def rank_files_by_complexity(files: List[str]) -> List[str]:
    """Rank files by complexity score (descending), skipping config/tool files.
    
    Args:
        files: List of absolute file paths
        
    Returns:
        Sorted list — most complex files first. Skipped files are
        appended at the end so they are still available for context.
    """
    ranked = []
    skipped = []
    
    for fp in files:
        basename = os.path.basename(fp)
        if basename in _SKIP_BASENAMES or ".config." in basename:
            skipped.append(fp)
            continue
        score = _file_complexity_score(fp)
        ranked.append((score, fp))
    
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [fp for _, fp in ranked] + skipped


