from contextlib import asynccontextmanager
from agents.extensions.models.litellm_model import LitellmModel
from fastapi import FastAPI
from agents import Agent, ModelSettings
from openai.types.shared import Reasoning
import os

from src.api.chat_application import get_doctor_id
from src.api.clients.postgres_sql_client import PostgresSQLClient, DatabaseConfig
from src.api.whatsapp_webhook_api import router as WhatsappRouter
from src.api.health_api import router as HealthRouter
from src.api.agent_tools import (
    get_available_slots,
    book_appointment,
    update_patient_details,
)

from src.api.telemetry import setup_tracing

model_settings = (
    ModelSettings(reasoning=Reasoning(effort="none"))
    if os.getenv("LLM_MODEL")
    else ModelSettings()
)


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
    get_doctor_id()  # fail at startup, not on the first chat message
    database_config = get_database_config()
    app.state.postgres_client = PostgresSQLClient(database_config)
    app.state.agent = Agent(
        name="assistant",
        model=os.getenv("LLM_MODEL") or LitellmModel(model=os.getenv("LITE_LLM_MODEL")),
        model_settings=model_settings,
        tools=[update_patient_details, get_available_slots, book_appointment],
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

setup_tracing(app)
