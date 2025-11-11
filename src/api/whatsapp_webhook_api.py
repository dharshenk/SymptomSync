from typing import Annotated
from api.models.IO_model import InputModel
from api.services.chat_history_service import ChatHistoryService
from api.clients.postgres_sql_client import PostgresSQLClient, DatabaseConfig
from api.models.chat_session_model import ChatMessage, SenderType
from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel
from dotenv import load_dotenv
from api.services.patient_service import PatientService
from contextlib import asynccontextmanager
import os
from fastapi import FastAPI, Depends

load_dotenv()


def get_database_config() -> DatabaseConfig:
    return DatabaseConfig(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        database=os.getenv("POSTGRES_DATABASE"),
        username=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def get_postgres_client() -> PostgresSQLClient:
    return app.state.postgres_client


def get_agent() -> Agent:
    return app.state.agent


def get_patient_service(
    postgres_client: Annotated[PostgresSQLClient, Depends(get_postgres_client)],
) -> PatientService:
    return PatientService(postgres_client)


def get_chat_history_service(
    postgres_client: Annotated[PostgresSQLClient, Depends(get_postgres_client)],
) -> ChatHistoryService:
    return ChatHistoryService(postgres_client)


@asynccontextmanager
async def lifespan(app: FastAPI):
    database_config = get_database_config()
    app.state.postgres_client = PostgresSQLClient(database_config)
    app.state.agent = Agent(
        name="assistant",
        model=LitellmModel(model="gemini/gemini-2.5-flash"),
        instructions="You're a helpful assistant. Who keeps it concise.",
    )

    yield

    if app.state.postgres_client:
        app.state.postgres_client.close()
        app.state.postgres_client = None

    if app.state.agent:
        app.state.agent = None


app = FastAPI(lifespan=lifespan)


def format_messages_for_runner(
    user_question: str, previous_messages: list["ChatMessage"] | None = None
) -> list[dict]:
    """
    Build a chat message list for OpenAI's Runner.
    Always appends the current user question, and prepends previous messages if given.
    """

    sender_type_map = {"patient": "user", "bot": "assistant"}

    messages: list[dict] = []

    if previous_messages:
        messages.extend(
            {
                "role": sender_type_map.get(msg.sender_type.lower()),
                "content": msg.message_content,
            }
            for msg in previous_messages
        )

    messages.append({"role": "user", "content": user_question})

    return messages


@app.post("/")
async def get_response(
    user_input: InputModel,
    patient_service: Annotated[PatientService, Depends(get_patient_service)],
    chat_history_service: Annotated[
        ChatHistoryService, Depends(get_chat_history_service)
    ],
    agent: Annotated[Agent, Depends(get_agent)],
):
    patient = await patient_service.get_patient_by_patient_id(
        user_input.patient.patient_id
    )
    if not patient:
        patient = await patient_service.create_patient(user_input.patient)

    chat_session = await chat_history_service.get_session(user_input.session_id)
    if not chat_session:
        chat_session = await chat_history_service.create_session(
            user_input.session_id, patient.id
        )

    previous_messages = await chat_history_service.get_session_messages(
        session_id=chat_session.id
    )

    user_message = ChatMessage(
        session_id=chat_session.id,
        sender_type=SenderType.patient,
        message_content=user_input.input,
        message_sequence=(
            previous_messages[-1].message_sequence + 1 if previous_messages else 1
        ),
    )
    await chat_history_service.add_message(user_message)

    input_list = format_messages_for_runner(
        user_question=user_input.input, previous_messages=previous_messages
    )

    # running the agent
    response = await Runner.run(starting_agent=agent, input=input_list)

    ai_message = ChatMessage(
        session_id=chat_session.id,
        sender_type=SenderType.bot,
        message_content=response.final_output,
        message_sequence=user_message.message_sequence + 1,
    )

    await chat_history_service.add_message(ai_message)

    return response.final_output
