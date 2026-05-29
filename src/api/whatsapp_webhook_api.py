from typing import Annotated
from jinja2 import Template
from src.api.services.chat_history_service import ChatHistoryService
from src.api.services.appointment_service import AppointmentService
from src.api.services.function_tool_service import ToolContext
from src.api.clients.postgres_sql_client import PostgresSQLClient
from src.api.models.chat_session_model import ChatMessage, SenderType
from src.api.models.patient_model import Patient
from src.api.models.telegram_model import TelegramUpdate
from src.api.clients.whatsapp_client import WhatsAppClient, WhatsAppConfig
from src.api.clients.telegram_client import TelegramClient, TelegramConfig
from src.api.services.patient_service import PatientService
from agents import Agent, Runner
from dotenv import load_dotenv
from fastapi import Depends, APIRouter, Request, Query, HTTPException
from fastapi.responses import PlainTextResponse
import uuid
import os
from datetime import date

load_dotenv()

SYSTEM_PROMPT_PATH = os.getenv("SYSTEM_PROMPT_PATH")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_RECIPIENT_NUMBER = os.getenv("WHATSAPP_RECIPIENT_NUMBER")


def get_postgres_client(request: Request) -> PostgresSQLClient:
    return request.app.state.postgres_client


def get_agent(request: Request) -> Agent:
    return request.app.state.agent


def get_telegram_client():
    return TelegramClient(TelegramConfig(bot_token=os.getenv("TELEGRAM_BOT_TOKEN")))


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


def get_appointment_service(
    postgres_client: Annotated[PostgresSQLClient, Depends(get_postgres_client)],
) -> AppointmentService:
    return AppointmentService(postgres_client)


router = APIRouter()


def format_messages_for_runner(
    user_question: str,
    system_prompt: str,
    previous_messages: list["ChatMessage"] | None = None,
) -> list[dict]:
    """
    Build a chat message list for OpenAI's Runner.
    Always appends the current user question, and prepends previous messages if given.
    """

    sender_type_map = {"patient": "user", "bot": "assistant"}

    messages: list[dict] = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

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


def get_system_prompt():
    with open(SYSTEM_PROMPT_PATH) as fp:
        raw_prompt_text = fp.read()

    template = Template(raw_prompt_text)
    today_str = date.today().strftime("%A, %B %d, %Y")
    system_prompt = template.render(current_date=today_str)

    return system_prompt


@router.post("/webhook")
async def get_response(
    # user_input: InputModel,
    # whatsapp_webhook_request: WhatsAppWebhookRequest,
    telegram_webhook_request: TelegramUpdate,
    patient_service: Annotated[PatientService, Depends(get_patient_service)],
    chat_history_service: Annotated[
        ChatHistoryService, Depends(get_chat_history_service)
    ],
    agent: Annotated[Agent, Depends(get_agent)],
    telegram_client: Annotated[TelegramClient, Depends(get_telegram_client)],
    appointment_service: Annotated[
        AppointmentService, Depends(get_appointment_service)
    ],
):
    patient_ph_no = str(telegram_webhook_request.message.from_user.id)
    session_id = uuid.uuid5(uuid.NAMESPACE_DNS, patient_ph_no)
    patient_message = telegram_webhook_request.message.text

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

    system_prompt = get_system_prompt()

    input_list = format_messages_for_runner(
        user_question=patient_message,
        previous_messages=previous_messages,
        system_prompt=system_prompt,
    )

    # Fetch the latest appointment for this patient
    latest_appointment = await appointment_service.get_appointment_by_patient_id(
        patient.id
    )

    tool_context = ToolContext(
        patient_id=patient.id,
        chat_session_id=chat_session.id,
        appointment_service=appointment_service,
        doctor_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        appointment=latest_appointment,
        appointment_date=(
            latest_appointment.appointment_date if latest_appointment else date.today()
        ),
    )

    # running the agent
    response = await Runner.run(
        starting_agent=agent, input=input_list, context=tool_context
    )

    ai_message = ChatMessage(
        session_id=chat_session.id,
        sender_type=SenderType.bot,
        message_content=response.final_output,
        message_sequence=user_message.message_sequence + 1,
    )

    await chat_history_service.add_message(ai_message)

    # whatsapp_client.send_text_message(to=WHATSAPP_RECIPIENT_NUMBER, message=response.final_output)
    telegram_client.send_message(patient_ph_no, response.final_output)

    return response.final_output


@router.get("/webhook")
async def verify(
    mode: str = Query(None, alias="hub.mode"),
    token: str = Query(None, alias="hub.verify_token"),
    challenge: str = Query(None, alias="hub.challenge"),
):
    if mode and token:
        if mode == "subscribe" and token == VERIFY_TOKEN:  # however you load config
            # logging.info("WEBHOOK_VERIFIED")
            return PlainTextResponse(content=challenge, status_code=200)
        else:
            # logging.info("VERIFICATION_FAILED")
            raise HTTPException(status_code=403, detail="Verification failed")
    else:
        # logging.info("MISSING_PARAMETER")
        raise HTTPException(status_code=400, detail="Missing parameters")
