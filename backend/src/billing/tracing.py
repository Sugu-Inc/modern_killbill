"""OpenTelemetry tracing configuration for distributed tracing."""
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from billing.config import settings


def setup_tracing(app) -> None:  # noqa: ANN001
    """
    Configure OpenTelemetry tracing with FastAPI and SQLAlchemy instrumentation.

    Args:
        app: FastAPI application instance
    """
    # Create resource with service name
    resource = Resource(attributes={SERVICE_NAME: settings.otel_service_name})

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Create OTLP exporter
    otlp_exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)

    # Add span processor
    processor = BatchSpanProcessor(otlp_exporter)
    provider.add_span_processor(processor)

    # Set global tracer provider
    trace.set_tracer_provider(provider)

    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)

    # Instrument SQLAlchemy
    # Note: This will be called after engine creation in database.py
    # For now, we just configure the instrumentor
    SQLAlchemyInstrumentor().instrument()


def get_tracer(name: str) -> trace.Tracer:
    """
    Get a tracer instance for creating custom spans.

    Args:
        name: Tracer name (typically module name)

    Returns:
        Tracer: OpenTelemetry tracer instance
    """
    return trace.get_tracer(name)
