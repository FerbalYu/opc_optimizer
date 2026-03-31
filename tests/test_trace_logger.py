"""Tests for utils/trace_logger.py (v2.6.0)."""

import os
import sys
import json
import pytest
import tempfile

# ─── Path setup ─────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.trace_logger import TraceLogger, TraceEntry, get_trace_logger


class TestTraceEntry:
    def test_create_entry(self):
        entry = TraceEntry(
            node_name="plan",
            round_number=1,
            model_name="openai/gpt-4o",
            input_messages=[{"role": "user", "content": "hello"}],
            output_text="world",
            prompt_tokens=10,
            completion_tokens=5,
            elapsed_seconds=1.23,
        )
        assert entry.node_name == "plan"
        assert entry.round_number == 1
        assert entry.prompt_tokens == 10

    def test_to_dict(self):
        entry = TraceEntry(node_name="execute", round_number=2)
        d = entry.to_dict()
        assert d["node_name"] == "execute"
        assert d["round_number"] == 2
        assert "timestamp" in d

    def test_from_dict(self):
        d = {
            "node_name": "test",
            "round_number": 3,
            "timestamp": "2025-01-01T00:00:00",
            "model_name": "minimax",
            "input_messages": [],
            "output_text": "ok",
            "prompt_tokens": 50,
            "completion_tokens": 20,
            "elapsed_seconds": 0.5,
        }
        entry = TraceEntry.from_dict(d)
        assert entry.node_name == "test"
        assert entry.prompt_tokens == 50


class TestTraceLogger:
    def test_log_and_retrieve(self):
        logger = TraceLogger()
        logger.set_context("plan", 1)
        logger.log(
            model_name="gpt-4",
            input_messages=[{"role": "user", "content": "test"}],
            output_text="response",
            prompt_tokens=100,
            completion_tokens=50,
        )
        entries = logger.get_round(1)
        assert len(entries) == 1
        assert entries[0]["node_name"] == "plan"
        assert entries[0]["model_name"] == "gpt-4"

    def test_multiple_rounds(self):
        logger = TraceLogger()
        logger.set_context("plan", 1)
        logger.log(model_name="m1", input_messages=[], output_text="a")
        logger.set_context("execute", 1)
        logger.log(model_name="m1", input_messages=[], output_text="b")
        logger.set_context("plan", 2)
        logger.log(model_name="m1", input_messages=[], output_text="c")

        r1 = logger.get_round(1)
        r2 = logger.get_round(2)
        assert len(r1) == 2
        assert len(r2) == 1
        assert r2[0]["node_name"] == "plan"

    def test_get_all_rounds(self):
        logger = TraceLogger()
        logger.log(model_name="m", input_messages=[], output_text="", round_number=1)
        logger.log(model_name="m", input_messages=[], output_text="", round_number=2)
        logger.log(model_name="m", input_messages=[], output_text="", round_number=2)
        all_rounds = logger.get_all_rounds()
        assert 1 in all_rounds
        assert 2 in all_rounds
        assert len(all_rounds[1]) == 1
        assert len(all_rounds[2]) == 2

    def test_entry_count(self):
        logger = TraceLogger()
        assert logger.entry_count == 0
        logger.log(model_name="m", input_messages=[], output_text="")
        logger.log(model_name="m", input_messages=[], output_text="")
        assert logger.entry_count == 2

    def test_save_round_jsonl(self):
        logger = TraceLogger()
        logger.set_context("execute", 1)
        logger.log(
            model_name="test-model",
            input_messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}],
            output_text="result",
            prompt_tokens=30,
            completion_tokens=10,
            elapsed_seconds=0.8,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = logger.save_round(tmpdir, 1)
            assert path is not None
            assert os.path.exists(path)
            
            # Verify JSONL format
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            assert len(lines) == 1
            entry = json.loads(lines[0])
            assert entry["model_name"] == "test-model"
            assert entry["prompt_tokens"] == 30

    def test_save_round_empty(self):
        logger = TraceLogger()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = logger.save_round(tmpdir, 99)
            assert path is None

    def test_load_round(self):
        logger = TraceLogger()
        logger.set_context("plan", 3)
        logger.log(model_name="loaded", input_messages=[], output_text="data")

        with tempfile.TemporaryDirectory() as tmpdir:
            logger.save_round(tmpdir, 3)
            loaded = TraceLogger.load_round(tmpdir, 3)
            assert len(loaded) == 1
            assert loaded[0]["model_name"] == "loaded"

    def test_load_round_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            loaded = TraceLogger.load_round(tmpdir, 999)
            assert loaded == []

    def test_export_round_json(self):
        logger = TraceLogger()
        logger.log(model_name="exp", input_messages=[], output_text="x", round_number=5)
        json_str = logger.export_round_json(5)
        data = json.loads(json_str)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["model_name"] == "exp"

    def test_context_setting(self):
        logger = TraceLogger()
        logger.set_context("archive", 7)
        logger.log(model_name="m", input_messages=[], output_text="")
        entries = logger.get_round(7)
        assert len(entries) == 1
        assert entries[0]["node_name"] == "archive"

    def test_explicit_overrides_context(self):
        """Explicit node_name/round_number should override set_context."""
        logger = TraceLogger()
        logger.set_context("plan", 1)
        logger.log(
            model_name="m", input_messages=[], output_text="",
            node_name="test", round_number=5,
        )
        assert logger.get_round(5)[0]["node_name"] == "test"
        assert logger.get_round(1) == []


class TestGetTraceLogger:
    def test_singleton(self):
        a = get_trace_logger()
        b = get_trace_logger()
        assert a is b
