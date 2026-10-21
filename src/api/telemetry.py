import functools
import inspect
import os
from typing import Any
from collections.abc import Callable

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer("symptom.sync.tracer")


def setup_tracing(app: FastAPI) -> None:
    """Trace requests only when an OTLP endpoint is explicitly configured."""
    if os.getenv("OTEL_SDK_DISABLED", "").strip().lower() == "true":
        return
    if not any(
        os.getenv(name, "").strip()
        for name in (
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
        )
    ):
        return

    provider = TracerProvider(
        resource=Resource.create(attributes={SERVICE_NAME: "symptom-sync"})
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)


def traced(name: str, attrs: Callable[..., dict[str, Any]] | None = None):
    """
    Wrap a sync or async function in a span called `name`.

    `attrs`, if given, is called with the function's arguments and returns the
    attributes to set on the span. Exceptions are recorded and mark the span as failed.
    """

    def decorator(func):
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                with tracer.start_as_current_span(name) as span:
                    if attrs:
                        span.set_attributes(attrs(*args, **kwargs))
                    return await func(*args, **kwargs)

        else:

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with tracer.start_as_current_span(name) as span:
                    if attrs:
                        span.set_attributes(attrs(*args, **kwargs))
                    return func(*args, **kwargs)

        return wrapper

    return decorator


def set_span_attributes(attributes: dict[str, Any]) -> None:
    """Set attributes on the currently active span."""
    trace.get_current_span().set_attributes(attributes)


def record_error(exc: Exception) -> None:
    """Mark the current span as failed, for exceptions that are handled rather than raised."""
    span = trace.get_current_span()
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))
