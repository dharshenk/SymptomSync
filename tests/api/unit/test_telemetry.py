from unittest.mock import patch

import pytest
from fastapi import FastAPI

from src.api import telemetry


@pytest.fixture
def tracing_components(monkeypatch):
    for name in (
        "OTEL_SDK_DISABLED",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    ):
        monkeypatch.delenv(name, raising=False)
    with (
        patch.object(telemetry, "TracerProvider") as provider,
        patch.object(telemetry, "OTLPSpanExporter") as exporter,
        patch.object(telemetry, "BatchSpanProcessor") as processor,
        patch.object(telemetry.trace, "set_tracer_provider") as set_provider,
        patch.object(telemetry.FastAPIInstrumentor, "instrument_app") as instrument,
    ):
        yield provider, exporter, processor, set_provider, instrument


@pytest.mark.parametrize("endpoint", [None, "", "   "])
def test_no_collector_leaves_tracing_disabled(
    monkeypatch, tracing_components, endpoint
):
    if endpoint is not None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint)

    telemetry.setup_tracing(FastAPI())

    for component in tracing_components:
        component.assert_not_called()


@pytest.mark.parametrize(
    "endpoint_name, endpoint",
    [
        ("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4318"),
        ("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://jaeger:4318/v1/traces"),
    ],
)
def test_configured_collector_enables_tracing(
    monkeypatch, tracing_components, endpoint_name, endpoint
):
    monkeypatch.setenv(endpoint_name, endpoint)
    provider, exporter, processor, set_provider, instrument = tracing_components
    app = FastAPI()

    telemetry.setup_tracing(app)

    exporter.assert_called_once_with()
    processor.assert_called_once_with(exporter.return_value)
    provider.return_value.add_span_processor.assert_called_once_with(
        processor.return_value
    )
    set_provider.assert_called_once_with(provider.return_value)
    instrument.assert_called_once_with(app)


@pytest.mark.parametrize("disabled", ["true", "TRUE", " True "])
def test_sdk_disabled_overrides_configured_collector(
    monkeypatch, tracing_components, disabled
):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4318")
    monkeypatch.setenv("OTEL_SDK_DISABLED", disabled)

    telemetry.setup_tracing(FastAPI())

    for component in tracing_components:
        component.assert_not_called()
