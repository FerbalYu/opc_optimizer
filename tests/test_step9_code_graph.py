"""Tests for Step 9 — code_graph module (AST symbol index + smart context)."""

import os
import ast
import pytest
from utils.code_graph import CodeGraph, Symbol, _PythonVisitor, build_project_index


class TestSymbol:
    def test_summary_line(self):
        sym = Symbol("hello", "function", "main.py", 1, 5,
                     signature="def hello(x: int) -> str",
                     docstring="Say hello.")
        line = sym.summary_line()
        assert "def hello" in line
        assert "Say hello" in line

    def test_to_dict(self):
        sym = Symbol("foo", "function", "a.py", 10, 20,
                     signature="def foo()", calls=["bar"])
        d = sym.to_dict()
        assert d["name"] == "foo"
        assert d["calls"] == ["bar"]


class TestPythonVisitor:
    def test_extracts_functions(self):
        code = '''
def hello(name: str) -> str:
    """Say hello."""
    return f"Hello {name}"

async def fetch(url):
    pass
'''
        tree = ast.parse(code)
        visitor = _PythonVisitor("test.py")
        visitor.visit(tree)
        names = [s.name for s in visitor.symbols]
        assert "hello" in names
        assert "fetch" in names
        
        hello = [s for s in visitor.symbols if s.name == "hello"][0]
        assert "str" in hello.signature
        assert "Say hello" in hello.docstring

    def test_extracts_classes_and_methods(self):
        code = '''
class Animal:
    """Base animal."""
    def speak(self):
        pass
    
class Dog(Animal):
    def speak(self):
        print("Woof")
'''
        tree = ast.parse(code)
        visitor = _PythonVisitor("test.py")
        visitor.visit(tree)
        names = [s.name for s in visitor.symbols]
        assert "Animal" in names
        assert "Dog" in names
        assert "Animal.speak" in names
        assert "Dog.speak" in names

    def test_extracts_imports(self):
        code = '''
import os
from typing import List, Dict
from utils.llm import LLMService
'''
        tree = ast.parse(code)
        visitor = _PythonVisitor("test.py")
        visitor.visit(tree)
        assert "os" in visitor.imports
        assert "typing.List" in visitor.imports

    def test_extracts_calls(self):
        code = '''
def main():
    data = read_file("x")
    result = process(data)
    print(result)
'''
        tree = ast.parse(code)
        visitor = _PythonVisitor("test.py")
        visitor.visit(tree)
        main = [s for s in visitor.symbols if s.name == "main"][0]
        assert "read_file" in main.calls
        assert "process" in main.calls
        assert "print" in main.calls


class TestCodeGraph:
    def test_build_index(self, tmp_path):
        (tmp_path / "main.py").write_text(
            'def hello():\n    print("hi")\n\nclass App:\n    pass\n',
            encoding="utf-8"
        )
        graph = CodeGraph(str(tmp_path))
        graph.build_index([str(tmp_path / "main.py")])
        assert "hello" in graph.symbols
        assert "App" in graph.symbols

    def test_get_file_signatures(self, tmp_path):
        (tmp_path / "utils.py").write_text(
            'def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n',
            encoding="utf-8"
        )
        graph = CodeGraph(str(tmp_path))
        graph.build_index([str(tmp_path / "utils.py")])
        sigs = graph.get_file_signatures("utils.py")
        assert "add" in sigs
        assert "sub" in sigs

    def test_get_project_summary(self, tmp_path):
        (tmp_path / "a.py").write_text("def foo(): pass\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("def bar(): pass\n", encoding="utf-8")
        graph = CodeGraph(str(tmp_path))
        graph.build_index([str(tmp_path / "a.py"), str(tmp_path / "b.py")])
        summary = graph.get_project_summary()
        assert "foo" in summary
        assert "bar" in summary

    def test_callers_callees(self, tmp_path):
        (tmp_path / "main.py").write_text(
            'from utils import helper\n\ndef main():\n    helper()\n',
            encoding="utf-8"
        )
        (tmp_path / "utils.py").write_text(
            'def helper():\n    print("help")\n',
            encoding="utf-8"
        )
        graph = CodeGraph(str(tmp_path))
        graph.build_index([str(tmp_path / "main.py"), str(tmp_path / "utils.py")])
        
        callers = graph.get_callers("helper")
        assert any(c.name == "main" for c in callers)

    def test_regex_fallback(self, tmp_path):
        (tmp_path / "app.js").write_text(
            'function greet(name) {\n  return "Hello " + name;\n}\n\nclass MyApp {\n}\n',
            encoding="utf-8"
        )
        graph = CodeGraph(str(tmp_path))
        graph.build_index([str(tmp_path / "app.js")])
        assert "greet" in graph.symbols
        assert "MyApp" in graph.symbols

    def test_cache_roundtrip(self, tmp_path):
        logs = tmp_path / ".opclog"
        logs.mkdir()
        (tmp_path / "test.py").write_text("def cached(): pass\n", encoding="utf-8")
        
        # First build
        g1 = CodeGraph(str(tmp_path))
        g1.build_index([str(tmp_path / "test.py")])
        assert "cached" in g1.symbols
        
        # Second build should use cache
        g2 = CodeGraph(str(tmp_path))
        g2.build_index([str(tmp_path / "test.py")])
        assert "cached" in g2.symbols
