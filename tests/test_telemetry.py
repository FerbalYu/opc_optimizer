"""Tests for the OpenTelemetry telemetry module (utils/telemetry.py).

Tests cover graceful degradation when OTel is not installed,
initialization, and the trace_span context manager.
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestTelemetryGracefulDegradation:
    """Test that telemetry works correctly without OpenTelemetry installed."""

    def test_trace_span_noop_when_not_initialized(self):
        """trace_span should be a no-op when not initialized."""
        from utils.telemetry import trace_span
        
        # Should not raise even without init
        with trace_span("test.span", {"key": "value"}) as span:
            assert span is None  # No-op returns None
            result = 1 + 1
        assert result == 2

    def test_init_tracing_noop_without_otel(self):
        """init_tracing should not crash when opentelemetry is not installed."""
        import utils.telemetry as tel
        original_has_otel = tel.HAS_OTEL
        tel.HAS_OTEL = False
        original_init = tel._initialized
        tel._initialized = False

        try:
            tel.init_tracing()  # Should not raise
        finally:
            tel.HAS_OTEL = original_has_otel
            tel._initialized = original_init

    def test_get_tracer_returns_none_without_otel(self):
        """get_tracer should return None when OTel is not available."""
        import utils.telemetry as tel
        original = tel.HAS_OTEL
        tel.HAS_OTEL = False

        try:
            result = tel.get_tracer()
            assert result is None
        finally:
            tel.HAS_OTEL = original


class TestTraceSpan:
    """Test the trace_span context manager behavior."""

    def test_trace_span_propagates_exceptions(self):
        """Exceptions inside trace_span should propagate normally."""
        from utils.telemetry import trace_span

        with pytest.raises(ValueError, match="test error"):
            with trace_span("test.error"):
                raise ValueError("test error")

    def test_trace_span_returns_value(self):
        """Code inside trace_span should execute normally."""
        from utils.telemetry import trace_span

        results = []
        with trace_span("test.compute"):
            results.append(42)
        
        assert results == [42]

    def test_trace_span_with_various_attribute_types(self):
        """trace_span should handle different attribute value types."""
        from utils.telemetry import trace_span

        # Should not raise with any of these
        with trace_span("test.attrs", {
            "str_val": "hello",
            "int_val": 42,
            "float_val": 3.14,
            "bool_val": True,
            "list_val": [1, 2, 3],  # Should be converted to str
        }):
            pass

    def test_trace_span_with_none_attributes(self):
        """trace_span should handle None attributes."""
        from utils.telemetry import trace_span

        with trace_span("test.none", None):
            pass  # Should not raise

    def test_trace_span_nested(self):
        """Nested trace_span calls should work correctly."""
        from utils.telemetry import trace_span

        with trace_span("outer"):
            with trace_span("inner"):
                result = "nested"
        
        assert result == "nested"


class TestInitTracing:
    """Test initialization behavior."""

    def test_double_init_is_safe(self):
        """Calling init_tracing twice should be safe."""
        import utils.telemetry as tel
        
        # If OTel is not installed, both calls should be no-ops
        original_init = tel._initialized
        try:
            tel._initialized = False
            tel.init_tracing()
            tel.init_tracing()  # Should not raise
        finally:
            tel._initialized = original_init
