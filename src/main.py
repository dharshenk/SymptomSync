from contextlib import asynccontextmanager
from agents.extensions.models.litellm_model import LitellmModel
from fastapi import FastAPI
from agents import Agent
import os

from api.clients.postgres_sql_client import PostgresSQLClient, DatabaseConfig
from api.whatsapp_webhook_api import router as WhatsappRouter
from api.services.function_tool_service import book_appointment, generate_patient_report


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
        model=LitellmModel(model="gemini/gemini-2.5-flash"),
        tools=[book_appointment, generate_patient_report],
    )

    yield

    if app.state.postgres_client:
        app.state.postgres_client.close()
        app.state.postgres_client = None

    if app.state.agent:
        app.state.agent = None


app = FastAPI(lifespan=lifespan)
app.include_router(WhatsappRouter)
