"""Code Reviewer — scans LLM-generated code for suspicious patterns before write.

Provides a safety layer between LLM output and file system writes.
"""

import re
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger("opc.code_reviewer")


# Each rule is (pattern, description, severity)
# severity: "block" = reject modification, "warn" = log warning but allow
SUSPICIOUS_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    # ── Arbitrary code execution ──
    (re.compile(r'\beval\s*\('), "eval() — arbitrary code execution", "block"),
    (re.compile(r'\bexec\s*\('), "exec() — arbitrary code execution", "block"),
    (re.compile(r'\b__import__\s*\('), "__import__() — dynamic import", "block"),
    (re.compile(r'\bcompile\s*\(.+["\']exec["\']\s*\)'), "compile(…, 'exec') — code compilation", "block"),

    # ── System command execution ──
    (re.compile(r'\bos\.system\s*\('), "os.system() — shell command execution", "block"),
    (re.compile(r'\bos\.popen\s*\('), "os.popen() — shell command execution", "block"),
    (re.compile(r'\bsubprocess\.call\s*\(.*shell\s*=\s*True'), "subprocess.call(shell=True) — shell injection risk", "block"),
    (re.compile(r'\bsubprocess\.run\s*\(.*shell\s*=\s*True'), "subprocess.run(shell=True) — shell injection risk", "block"),
    (re.compile(r'\bsubprocess\.Popen\s*\(.*shell\s*=\s*True'), "subprocess.Popen(shell=True) — shell injection risk", "block"),

    # ── Destructive file operations ──
    (re.compile(r'\bshutil\.rmtree\s*\('), "shutil.rmtree() — recursive directory deletion", "block"),
    (re.compile(r'\bos\.rmdir\s*\('), "os.rmdir() — directory deletion", "warn"),
    (re.compile(r'\bos\.remove\s*\('), "os.remove() — file deletion", "warn"),
    (re.compile(r'\bos\.unlink\s*\('), "os.unlink() — file deletion", "warn"),

    # ── Network / exfiltration ──
    (re.compile(r'\burllib\.request\b'), "urllib.request — network access", "warn"),
    (re.compile(r'\brequests\.(get|post|put|delete|patch)\s*\('), "requests HTTP call — network access", "warn"),
    (re.compile(r'\bsocket\.\w+\s*\('), "socket operations — network access", "warn"),
    (re.compile(r'\bhttp\.client\b'), "http.client — network access", "warn"),

    # ── Encoding tricks ──
    (re.compile(r'\bbase64\.b64decode\s*\('), "base64.b64decode() — potential obfuscation", "warn"),
    (re.compile(r'\bcodecs\.decode\s*\(.*rot'), "codecs rot13 decode — obfuscation", "warn"),

    # ── Environment manipulation ──
    (re.compile(r'\bos\.environ\b.*='), "os.environ modification — env tampering", "warn"),

    # ── JavaScript / Node.js specific ──
    (re.compile(r'\bchild_process\b'), "child_process — Node.js command execution", "block"),
    (re.compile(r'\brequire\s*\(\s*["\']child_process["\']\s*\)'), "require('child_process') — Node.js shell", "block"),
]


class CodeReviewer:
    """Scans code content for suspicious patterns.

    Usage:
        reviewer = CodeReviewer()
        is_safe, issues = reviewer.review("new code content here")
        if not is_safe:
            # reject the modification
    """

    def __init__(self, extra_patterns: Optional[List[Tuple[re.Pattern, str, str]]] = None):
        self.patterns = list(SUSPICIOUS_PATTERNS)
        if extra_patterns:
            self.patterns.extend(extra_patterns)

    def review(self, code: str) -> Tuple[bool, List[str]]:
        """Review code content for suspicious patterns.

        Returns:
            (is_safe, issues): is_safe is False if any "block" pattern matched.
            issues is a list of human-readable descriptions of all matches.
        """
        issues: List[str] = []
        has_block = False

        for pattern, description, severity in self.patterns:
            matches = pattern.findall(code)
            if matches:
                prefix = "🚫 BLOCKED" if severity == "block" else "⚠️ WARNING"
                msg = f"{prefix}: {description} (found {len(matches)}x)"
                issues.append(msg)
                if severity == "block":
                    has_block = True
                logger.warning(msg)

        is_safe = not has_block
        return is_safe, issues
