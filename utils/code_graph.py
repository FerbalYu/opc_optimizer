"""Code graph — AST-based Python symbol indexing + smart context retrieval (v2.5.0).

Parses Python files to extract function/class signatures, import relations,
and call graphs. Provides on-demand context retrieval that significantly
reduces token usage when feeding code to LLMs.

For non-Python files, falls back to regex-based extraction.
"""

import os
import ast
import re
import json
import logging
import hashlib
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("opc.code_graph")

# ─── Symbol Types ─────────────────────────────────────────────────────

class Symbol:
    """Represents a code symbol (function, class, variable)."""
    __slots__ = ("name", "kind", "file", "line", "end_line", "signature",
                 "docstring", "calls", "decorators")
    
    def __init__(self, name: str, kind: str, file: str, line: int,
                 end_line: int = 0, signature: str = "",
                 docstring: str = "", calls: List[str] = None,
                 decorators: List[str] = None):
        self.name = name
        self.kind = kind  # "function", "class", "method", "import"
        self.file = file
        self.line = line
        self.end_line = end_line or line
        self.signature = signature
        self.docstring = docstring or ""
        self.calls = calls or []
        self.decorators = decorators or []
    
    def to_dict(self) -> dict:
        return {
            "name": self.name, "kind": self.kind, "file": self.file,
            "line": self.line, "end_line": self.end_line,
            "signature": self.signature, "docstring": self.docstring[:200],
            "calls": self.calls, "decorators": self.decorators,
        }

    def summary_line(self) -> str:
        """One-line summary for LLM context."""
        dec = " ".join(f"@{d}" for d in self.decorators)
        doc = f'  """{self.docstring[:80]}"""' if self.docstring else ""
        prefix = f"{dec} " if dec else ""
        return f"{prefix}{self.signature}{doc}"


# ─── AST Visitor ──────────────────────────────────────────────────────

class _PythonVisitor(ast.NodeVisitor):
    """Extract symbols from a Python AST."""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.symbols: List[Symbol] = []
        self.imports: List[str] = []
        self._current_class: Optional[str] = None
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._extract_func(node)
        self.generic_visit(node)
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._extract_func(node, is_async=True)
        self.generic_visit(node)
    
    def _extract_func(self, node, is_async=False):
        # Build signature
        args = []
        for arg in node.args.args:
            name = arg.arg
            ann = ""
            if arg.annotation:
                try:
                    ann = f": {ast.unparse(arg.annotation)}"
                except Exception:
                    ann = ": ..."
            args.append(f"{name}{ann}")
        
        returns = ""
        if node.returns:
            try:
                returns = f" -> {ast.unparse(node.returns)}"
            except Exception:
                returns = " -> ..."
        
        prefix = "async " if is_async else ""
        kind = "method" if self._current_class else "function"
        full_name = f"{self._current_class}.{node.name}" if self._current_class else node.name
        sig = f"{prefix}def {full_name}({', '.join(args)}){returns}"
        
        # Extract calls within the function body
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                try:
                    calls.append(ast.unparse(child.func))
                except Exception:
                    pass
        
        # Decorators
        decorators = []
        for dec in node.decorator_list:
            try:
                decorators.append(ast.unparse(dec))
            except Exception:
                pass
        
        # Docstring
        docstring = ast.get_docstring(node) or ""
        
        self.symbols.append(Symbol(
            name=full_name, kind=kind, file=self.filepath,
            line=node.lineno, end_line=node.end_lineno or node.lineno,
            signature=sig, docstring=docstring,
            calls=list(set(calls))[:20], decorators=decorators,
        ))
    
    def visit_ClassDef(self, node: ast.ClassDef):
        bases = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except Exception:
                bases.append("...")
        
        sig = f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"
        docstring = ast.get_docstring(node) or ""
        
        self.symbols.append(Symbol(
            name=node.name, kind="class", file=self.filepath,
            line=node.lineno, end_line=node.end_lineno or node.lineno,
            signature=sig, docstring=docstring,
        ))
        
        old_class = self._current_class
        self._current_class = node.name
        self.generic_visit(node)
        self._current_class = old_class
    
    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(alias.name)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            self.imports.append(f"{module}.{alias.name}")


# ─── Code Graph ───────────────────────────────────────────────────────

class CodeGraph:
    """Builds and queries a code symbol index for a project."""
    
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.symbols: Dict[str, Symbol] = {}  # name -> Symbol
        self.file_symbols: Dict[str, List[Symbol]] = {}  # file -> [symbols]
        self.file_imports: Dict[str, List[str]] = {}  # file -> [import strings]
        self._file_hashes: Dict[str, str] = {}
        self._cache_path = os.path.join(project_path, ".opclog", ".code_index.json")
    
    def build_index(self, files: List[str] = None):
        """Build or incrementally update the symbol index.
        
        Args:
            files: Optional list of absolute file paths. If None, scans project.
        """
        if files is None:
            from utils.file_ops import get_project_files
            files = get_project_files(self.project_path)
        
        # Try loading cache
        cached = self._load_cache()
        
        updated = 0
        for fp in files:
            rel = os.path.relpath(fp, self.project_path).replace("\\", "/")
            
            # Check if file changed (by content hash)
            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                continue
            
            file_hash = hashlib.md5(content.encode()).hexdigest()
            
            if rel in cached and cached[rel].get("hash") == file_hash:
                # Use cached symbols
                for sd in cached[rel].get("symbols", []):
                    sym = Symbol(**{k: sd[k] for k in Symbol.__slots__ if k in sd})
                    self.symbols[sym.name] = sym
                    self.file_symbols.setdefault(rel, []).append(sym)
                self.file_imports[rel] = cached[rel].get("imports", [])
                self._file_hashes[rel] = file_hash
                continue
            
            # Parse file
            if fp.endswith(".py"):
                self._parse_python(rel, content)
            else:
                self._parse_regex(rel, content)
            
            self._file_hashes[rel] = file_hash
            updated += 1
        
        # Save cache
        if updated > 0:
            self._save_cache()
            logger.info(f"Code index: {len(self.symbols)} symbols from {len(self.file_symbols)} files ({updated} updated)")
        else:
            logger.info(f"Code index: {len(self.symbols)} symbols (all cached)")
    
    def _parse_python(self, rel_path: str, content: str):
        """Parse a Python file using AST."""
        try:
            tree = ast.parse(content, filename=rel_path)
            visitor = _PythonVisitor(rel_path)
            visitor.visit(tree)
            
            for sym in visitor.symbols:
                self.symbols[sym.name] = sym
            self.file_symbols[rel_path] = visitor.symbols
            self.file_imports[rel_path] = visitor.imports
        except SyntaxError:
            self._parse_regex(rel_path, content)
    
    def _parse_regex(self, rel_path: str, content: str):
        """Regex fallback for non-Python files or syntax errors."""
        symbols = []
        
        # Match function/method definitions
        for m in re.finditer(r'^(?:export\s+)?(?:async\s+)?(?:def|function|func|fn)\s+(\w+)', content, re.MULTILINE):
            symbols.append(Symbol(
                name=m.group(1), kind="function", file=rel_path,
                line=content[:m.start()].count('\n') + 1,
                signature=m.group(0).strip(),
            ))
        
        # Match class definitions
        for m in re.finditer(r'^(?:export\s+)?class\s+(\w+)', content, re.MULTILINE):
            symbols.append(Symbol(
                name=m.group(1), kind="class", file=rel_path,
                line=content[:m.start()].count('\n') + 1,
                signature=m.group(0).strip(),
            ))
        
        for sym in symbols:
            self.symbols[sym.name] = sym
        if symbols:
            self.file_symbols[rel_path] = symbols
    
    # ─── Query Methods ─────────────────────────────────────────────
    
    def get_file_signatures(self, rel_path: str) -> str:
        """Get all function/class signatures for a file as a compact string."""
        syms = self.file_symbols.get(rel_path, [])
        if not syms:
            return ""
        lines = [f"# {rel_path}"]
        for s in syms:
            lines.append(f"  L{s.line}: {s.summary_line()}")
        return "\n".join(lines)
    
    def get_project_summary(self) -> str:
        """Get a compact project overview: file tree + all signatures."""
        sections = []
        for rel_path in sorted(self.file_symbols.keys()):
            sig_block = self.get_file_signatures(rel_path)
            if sig_block:
                sections.append(sig_block)
        return "\n\n".join(sections) if sections else "(no symbols found)"
    
    def get_callers(self, func_name: str) -> List[Symbol]:
        """Find symbols that call the given function."""
        callers = []
        for sym in self.symbols.values():
            if func_name in sym.calls:
                callers.append(sym)
        return callers
    
    def get_callees(self, func_name: str) -> List[Symbol]:
        """Find symbols that are called by the given function."""
        sym = self.symbols.get(func_name)
        if not sym:
            return []
        callees = []
        for call_name in sym.calls:
            # Try exact match first, then partial
            if call_name in self.symbols:
                callees.append(self.symbols[call_name])
            else:
                # Try matching method calls like self.foo -> CurrentClass.foo
                short = call_name.split(".")[-1]
                if short in self.symbols:
                    callees.append(self.symbols[short])
        return callees
    
    def get_smart_context(self, target_files: List[str], 
                          plan_text: str = "") -> str:
        """Build smart context for the execute node.
        
        Strategy:
        - Target files: full content
        - Files that call or are called by target functions: signatures only
        - Other mentioned files: signatures only
        
        This dramatically reduces token usage vs reading all files fully.
        """
        from utils.file_ops import read_file
        
        context_parts = []
        seen_files = set()
        
        # 1. Target files get full content
        for rel_path in target_files:
            abs_path = os.path.join(self.project_path, rel_path)
            if os.path.exists(abs_path):
                content = read_file(abs_path)
                if len(content) > 6000:
                    content = content[:6000] + "\n... (truncated)"
                context_parts.append(f"### {rel_path} (full)\n```\n{content}\n```")
                seen_files.add(rel_path)
        
        # 2. Find upstream/downstream dependencies via call graph
        dep_files = set()
        for rel_path in target_files:
            for sym in self.file_symbols.get(rel_path, []):
                # Callers of this file's functions
                for caller in self.get_callers(sym.name):
                    dep_files.add(caller.file)
                # Callees of this file's functions
                for callee in self.get_callees(sym.name):
                    dep_files.add(callee.file)
        
        # 3. Add dependency signatures (compact)
        for dep in sorted(dep_files):
            if dep not in seen_files:
                sigs = self.get_file_signatures(dep)
                if sigs:
                    context_parts.append(f"### {dep} (signatures)\n{sigs}")
                    seen_files.add(dep)
        
        return "\n\n".join(context_parts) if context_parts else ""
    
    # ─── Cache ─────────────────────────────────────────────────────
    
    def _load_cache(self) -> dict:
        """Load cached index from disk."""
        try:
            if os.path.exists(self._cache_path):
                with open(self._cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}
    
    def _save_cache(self):
        """Save index cache to disk."""
        try:
            cache = {}
            for rel_path, syms in self.file_symbols.items():
                cache[rel_path] = {
                    "hash": self._file_hashes.get(rel_path, ""),
                    "symbols": [s.to_dict() for s in syms],
                    "imports": self.file_imports.get(rel_path, []),
                }
            os.makedirs(os.path.dirname(self._cache_path), exist_ok=True)
            with open(self._cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save code index cache: {e}")


# ─── Convenience Functions ────────────────────────────────────────────

def build_project_index(project_path: str) -> CodeGraph:
    """Build a CodeGraph for the given project."""
    graph = CodeGraph(project_path)
    graph.build_index()
    return graph
