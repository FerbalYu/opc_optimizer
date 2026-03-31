"""OpenTelemetry tracing utilities for OPC Optimizer.

Provides graceful degradation — if opentelemetry is not installed,
all tracing calls become no-ops and the optimizer runs normally.

Usage:
    from utils.telemetry import init_tracing, trace_span

    # At startup
    init_tracing()

    # In any function
    with trace_span("my_operation", {"key": "value"}):
        do_work()
"""

import os
import logging
from contextlib import contextmanager
from typing import Optional, Dict, Any

logger = logging.getLogger("opc.telemetry")

# ─── Try to import OpenTelemetry ──────────────────────────────────
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        ConsoleSpanExporter,
        BatchSpanProcessor,
        SimpleSpanProcessor,
    )
    from opentelemetry.sdk.resources import Resource

    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False

_initialized = False
_tracer = None


def init_tracing(
    service_name: str = "opc-optimizer",
    endpoint: Optional[str] = None,
    console: bool = False,
):
    """Initialize OpenTelemetry tracing.

    Args:
        service_name: Service name for the tracer resource.
        endpoint: Optional OTLP endpoint (e.g. "http://localhost:4317").
                  If not set, checks OTEL_EXPORTER_OTLP_ENDPOINT env var.
        console: If True, also print spans to console (for debugging).
    """
    global _initialized, _tracer

    if not HAS_OTEL:
        logger.debug("OpenTelemetry not installed, tracing disabled")
        return

    if _initialized:
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    # OTLP exporter (if endpoint available)
    otlp_endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info(f"OTLP tracing enabled → {otlp_endpoint}")
        except ImportError:
            logger.warning(
                "opentelemetry-exporter-otlp-proto-grpc not installed, "
                "skipping OTLP export"
            )

    # Console exporter (for debugging)
    if console or os.getenv("OTEL_TRACE_CONSOLE", "").lower() in ("1", "true"):
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        logger.info("Console trace exporter enabled")

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("opc")
    _initialized = True
    logger.info("OpenTelemetry tracing initialized")


def get_tracer(name: str = "opc"):
    """Get a tracer instance. Returns a no-op tracer if OTel is not installed."""
    if not HAS_OTEL:
        return None
    if _tracer:
        return _tracer
    return trace.get_tracer(name)


@contextmanager
def trace_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
):
    """Context manager that creates a tracing span.

    If OpenTelemetry is not installed, this is a no-op.

    Args:
        name: Span name (e.g. "node.plan", "llm.call")
        attributes: Optional key-value attributes for the span

    Usage:
        with trace_span("node.plan", {"round": 1}):
            result = plan_node(state)
    """
    if not HAS_OTEL or not _initialized:
        yield None
        return

    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                # OTel attributes must be str/int/float/bool
                if isinstance(v, (str, int, float, bool)):
                    span.set_attribute(k, v)
                else:
                    span.set_attribute(k, str(v))
        try:
            yield span
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            raise
