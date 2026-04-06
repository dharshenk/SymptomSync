from typing import Annotated
from api.models.IO_model import WhatsAppWebhookRequest
from api.services.chat_history_service import ChatHistoryService
from api.clients.postgres_sql_client import PostgresSQLClient
from api.models.chat_session_model import ChatMessage, SenderType
from api.models.patient_model import Patient
from api.clients.whatsapp_client import WhatsAppClient, WhatsAppConfig
from agents import Agent, Runner
from dotenv import load_dotenv
from api.services.patient_service import PatientService
from fastapi import Depends, APIRouter, Request
import uuid
import os

load_dotenv()


def get_postgres_client(request: Request) -> PostgresSQLClient:
    return request.app.state.postgres_client


def get_agent(request: Request) -> Agent:
    return request.app.state.agent


def get_whatsapp_client():
    return WhatsAppClient(
        WhatsAppConfig(
            access_token=os.getenv("WHATSAPP_ACCESS_TOKEN"),
            phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID"),
        )
    )


def get_patient_service(
    postgres_client: Annotated[PostgresSQLClient, Depends(get_postgres_client)],
) -> PatientService:
    return PatientService(postgres_client)


def get_chat_history_service(
    postgres_client: Annotated[PostgresSQLClient, Depends(get_postgres_client)],
) -> ChatHistoryService:
    return ChatHistoryService(postgres_client)


router = APIRouter()


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


@router.post("/")
async def get_response(
    # user_input: InputModel,
    whatsapp_webhook_request: WhatsAppWebhookRequest,
    patient_service: Annotated[PatientService, Depends(get_patient_service)],
    chat_history_service: Annotated[
        ChatHistoryService, Depends(get_chat_history_service)
    ],
    agent: Annotated[Agent, Depends(get_agent)],
    whatsapp_client: Annotated[WhatsAppClient, Depends(get_whatsapp_client)],
):
    patient_ph_no = whatsapp_webhook_request.entry[0].changes[0].value.messages[0].from_
    session_id = uuid.uuid5(uuid.NAMESPACE_DNS, patient_ph_no)
    patient_message = (
        whatsapp_webhook_request.entry[0].changes[0].value.messages[0].text.body
    )

    patient = await patient_service.get_patient_by_patient_ph_no(patient_ph_no)
    if not patient:
        patient = await patient_service.create_patient(
            Patient(patient_ph_no=patient_ph_no)
        )

    chat_session = await chat_history_service.get_session(session_id)
    if not chat_session:
        chat_session = await chat_history_service.create_session(session_id, patient.id)

    previous_messages = await chat_history_service.get_session_messages(
        session_id=chat_session.id
    )

    user_message = ChatMessage(
        session_id=chat_session.id,
        sender_type=SenderType.patient,
        message_content=patient_message,  # Message.text.body
        message_sequence=(
            previous_messages[-1].message_sequence + 1 if previous_messages else 1
        ),
    )
    await chat_history_service.add_message(user_message)

    input_list = format_messages_for_runner(
        user_question=patient_message, previous_messages=previous_messages
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

    whatsapp_client.send_text_message(to="918610432661", message=response.final_output)

    return response.final_output
