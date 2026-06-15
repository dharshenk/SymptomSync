from contextlib import asynccontextmanager
from agents.extensions.models.litellm_model import LitellmModel
from fastapi import FastAPI
from agents import Agent
import os

from src.api.clients.postgres_sql_client import PostgresSQLClient, DatabaseConfig
from src.api.whatsapp_webhook_api import router as WhatsappRouter
from src.api.health_api import router as HealthRouter
from src.api.services.function_tool_service import (
    book_appointment,
    generate_patient_report,
    get_available_slots,
)

from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

resource = Resource.create(attributes={SERVICE_NAME: "symptom-sync"})

tracerProvider = TracerProvider(resource=resource)
processor = BatchSpanProcessor(
    OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")
)
tracerProvider.add_span_processor(processor)
trace.set_tracer_provider(tracerProvider)


def get_database_config() -> DatabaseConfig:
    return DatabaseConfig(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        database=os.getenv("POSTGRES_DATABASE"),
        username=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_config = get_database_config()
    app.state.postgres_client = PostgresSQLClient(database_config)
    app.state.agent = Agent(
        name="assistant",
        model=LitellmModel(model=os.getenv("LLM_MODEL")),
        tools=[book_appointment, generate_patient_report, get_available_slots],
    )

    yield

    if app.state.postgres_client:
        app.state.postgres_client.close()
        app.state.postgres_client = None

    if app.state.agent:
        app.state.agent = None


app = FastAPI(lifespan=lifespan)
app.include_router(WhatsappRouter)
app.include_router(HealthRouter)

# FastAPIInstrumentor.instrument_app(app)
