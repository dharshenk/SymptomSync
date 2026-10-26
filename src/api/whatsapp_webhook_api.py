from typing import Annotated
from jinja2 import Template
from src.api.services.chat_history_service import ChatHistoryService
from src.api.services.appointment_service import AppointmentService
from src.api.agent_tools import ToolContext
from src.api.clients.postgres_sql_client import PostgresSQLClient
from src.api.models.chat_session_model import ChatMessage, SenderType
from src.api.models.patient_intake_model import PatientIntakeState
from src.api.models.patient_model import Patient
from src.api.models.pending_approval_model import PendingApproval
from src.api.models.telegram_model import (
    CallbackQuery,
    Message,
    TelegramWebhookUpdate,
)
from src.api.clients.whatsapp_client import WhatsAppClient, WhatsAppConfig
from src.api.clients.telegram_client import (
    TelegramAPIError,
    TelegramClient,
    TelegramConfig,
)
from src.api.services.patient_service import PatientService
from src.api.services.patient_intake_service import PatientIntakeService
from src.api.services.pending_approval_service import PendingApprovalService
from agents import Agent, RunContextWrapper, RunState, Runner, ToolApprovalItem
from dotenv import load_dotenv
from fastapi import Depends, APIRouter, HTTPException, Request
import logging
import uuid
import os
from datetime import date

from src.api.telemetry import traced, set_span_attributes

load_dotenv()

SYSTEM_PROMPT_PATH = os.getenv("SYSTEM_PROMPT_PATH")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_RECIPIENT_NUMBER = os.getenv("WHATSAPP_RECIPIENT_NUMBER")

logger = logging.getLogger(__name__)

DOCTOR_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

APPROVE = "approve"
CHANGES_NEEDED = "changes_needed"
CHANGES_REJECTION_MESSAGE = (
    "The patient chose 'Changes needed', so the appointment was NOT booked. "
    "Ask the patient which details they want to change, save them with "
    "update_patient_details, then call book_appointment again."
)


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


def get_patient_intake_service(
    postgres_client: Annotated[PostgresSQLClient, Depends(get_postgres_client)],
) -> PatientIntakeService:
    return PatientIntakeService(postgres_client)


def get_pending_approval_service(
    postgres_client: Annotated[PostgresSQLClient, Depends(get_postgres_client)],
) -> PendingApprovalService:
    return PendingApprovalService(postgres_client)


router = APIRouter()


def messages_to_agent_items(previous_messages: list["ChatMessage"]) -> list[dict]:
    """Convert stored chat messages into plain role/content agent input items."""

    sender_type_map = {"patient": "user", "bot": "assistant"}

    return [
        {
            "role": sender_type_map.get(msg.sender_type.lower()),
            "content": msg.message_content,
        }
        for msg in previous_messages
    ]


def format_messages_for_runner(
    user_question: str,
    system_prompt: str,
    previous_items: list[dict] | None = None,
) -> list[dict]:
    """
    Build the input item list for OpenAI's Runner.
    Always appends the current user question, and prepends previous agent items
    (messages, tool calls and tool outputs) if given.
    """

    messages: list[dict] = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    if previous_items:
        messages.extend(previous_items)

    messages.append({"role": "user", "content": user_question})

    return messages


def get_system_prompt():
    with open(SYSTEM_PROMPT_PATH) as fp:
        raw_prompt_text = fp.read()

    template = Template(raw_prompt_text)
    today_str = date.today().strftime("%A, %B %d, %Y")
    system_prompt = template.render(current_date=today_str)

    return system_prompt


def session_id_for(sender_id: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, sender_id)


@traced("agent.run")
async def run_agent(
    agent: Agent, agent_input: list[dict] | RunState, context: ToolContext | None = None
):
    # A resumed RunState carries its own context (with the approval decisions);
    # passing `context` would replace it and drop them.
    if isinstance(agent_input, RunState):
        return await Runner.run(starting_agent=agent, input=agent_input)
    return await Runner.run(starting_agent=agent, input=agent_input, context=context)


async def build_tool_context(
    patient: Patient,
    chat_session_id: uuid.UUID,
    appointment_service: AppointmentService,
    patient_intake_service: PatientIntakeService,
) -> ToolContext:
    latest_appointment = await appointment_service.get_appointment_by_patient_id(
        patient.id
    )

    patient_intake_state = await patient_intake_service.get_intake_state(
        chat_session_id
    )
    if not patient_intake_state:
        patient_intake_state = await patient_intake_service.create_intake_state(
            PatientIntakeState(chat_session_id=chat_session_id)
        )

    return ToolContext(
        patient_id=patient.id,
        chat_session_id=chat_session_id,
        appointment_service=appointment_service,
        patient_intake_service=patient_intake_service,
        patient_intake_state=patient_intake_state,
        doctor_id=DOCTOR_ID,
        appointment=latest_appointment,
        appointment_date=(
            latest_appointment.appointment_date if latest_appointment else date.today()
        ),
    )


def approval_prompt(intake_state: PatientIntakeState) -> dict:
    """Booking summary with Go Ahead / Changes needed buttons (Telegram format)."""
    details = [
        ("Name", intake_state.name),
        ("Age", intake_state.age),
        ("Gender", intake_state.gender),
        ("Symptoms", intake_state.symptoms),
        ("Pre-existing conditions", intake_state.pre_existing_conditions),
        ("Medications", intake_state.medications),
        (
            "Date",
            (
                intake_state.preferred_date.strftime("%A, %B %d, %Y")
                if intake_state.preferred_date
                else None
            ),
        ),
        (
            "Start time",
            (
                intake_state.preferred_start_time.strftime("%I:%M %p")
                if intake_state.preferred_start_time
                else None
            ),
        ),
    ]
    lines = [f"{label}: {value}" for label, value in details if value is not None]
    text = (
        "Please review your appointment details:\n\n"
        + "\n".join(lines)
        + "\n\nShall I go ahead and book it?"
    )
    return {
        "text": text,
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "Go Ahead", "callback_data": APPROVE}],
                [{"text": "Changes needed", "callback_data": CHANGES_NEEDED}],
            ]
        },
    }


def deliver_reply(telegram_client: TelegramClient, chat_id: str, reply: str | dict):
    """Push a reply to the chat; a dict is a prompt with `text` and `reply_markup`.

    A failed send is logged, not raised: the run is already persisted, and an
    error response would make Telegram redeliver the update and re-run the agent.
    """
    prompt = reply if isinstance(reply, dict) else {"text": reply}
    try:
        telegram_client.send_message(chat_id, **prompt)
    except TelegramAPIError:
        logger.exception("Failed to send Telegram reply to chat_id=%s", chat_id)


def acknowledge_button_press(telegram_client: TelegramClient, callback_query_id: str):
    """Stop the button's loading spinner; a failure is logged, not raised.

    Telegram only accepts this for a short time after the press, and the
    decision can still be processed without it.
    """
    try:
        telegram_client.answer_callback_query(callback_query_id)
    except TelegramAPIError:
        logger.exception("Failed to answer callback_query_id=%s", callback_query_id)


def remove_buttons(telegram_client: TelegramClient, callback_query: CallbackQuery):
    """Take the buttons off the pressed message; a failure is logged, not raised."""
    if callback_query.message is None:
        return
    try:
        telegram_client.remove_inline_keyboard(
            str(callback_query.message.chat.id), callback_query.message.message_id
        )
    except TelegramAPIError:
        logger.exception(
            "Failed to remove buttons from message_id=%s",
            callback_query.message.message_id,
        )


async def finalize_run(
    result,
    tool_context: ToolContext,
    user_item: dict,
    user_message_sequence: int,
    chat_history_service: ChatHistoryService,
    pending_approval_service: PendingApprovalService,
    telegram_client: TelegramClient,
    chat_id: str,
):
    """Persist a finished run, or save a paused one until the patient decides.

    Either way the reply is sent to the chat and also returned as the response.
    """
    chat_session_id = tool_context.chat_session_id

    if result.interruptions:
        await pending_approval_service.save(
            PendingApproval(
                chat_session_id=chat_session_id,
                run_state=result.to_state().to_string(context_serializer=lambda _: {}),
                user_item=user_item,
                user_message_sequence=user_message_sequence,
            )
        )
        prompt = approval_prompt(tool_context.patient_intake_state)
        deliver_reply(telegram_client, chat_id, prompt)
        return prompt

    ai_message = ChatMessage(
        session_id=chat_session_id,
        sender_type=SenderType.bot,
        message_content=result.final_output,
        message_sequence=user_message_sequence + 1,
    )
    await chat_history_service.add_message(ai_message)

    await chat_history_service.add_agent_items(
        chat_session_id,
        [user_item]
        + [
            item.to_input_item()
            for item in result.new_items
            if not isinstance(item, ToolApprovalItem)
        ],
    )
    await pending_approval_service.delete(chat_session_id)

    # whatsapp_client.send_text_message(to=WHATSAPP_RECIPIENT_NUMBER, message=result.final_output)
    deliver_reply(telegram_client, chat_id, result.final_output)

    return result.final_output


async def handle_message(
    message: Message,
    patient_service: PatientService,
    chat_history_service: ChatHistoryService,
    patient_intake_service: PatientIntakeService,
    pending_approval_service: PendingApprovalService,
    agent: Agent,
    telegram_client: TelegramClient,
    appointment_service: AppointmentService,
):
    """Run the agent on a patient's chat message."""
    patient_ph_no = str(message.from_user.id)
    session_id = session_id_for(patient_ph_no)
    today_str = date.today().strftime("%A, %B %d, %Y")
    patient_message = f"[Current date: {today_str}]\n{message.text}"

    patient = await patient_service.get_patient_by_patient_ph_no(patient_ph_no)
    if not patient:
        patient = await patient_service.create_patient(
            Patient(patient_ph_no=patient_ph_no)
        )

    chat_session = await chat_history_service.get_session(session_id)
    if not chat_session:
        chat_session = await chat_history_service.create_session(session_id, patient.id)

    set_span_attributes(
        {"patient.id": str(patient.id), "chat_session.id": str(chat_session.id)}
    )

    # A run is paused (or its decision is being applied): don't start another one.
    pending = await pending_approval_service.get(chat_session.id)
    if pending and pending.status == "processing":
        reply = "Still working on your booking, one moment."
        deliver_reply(telegram_client, patient_ph_no, reply)
        return reply
    if pending:
        intake_state = await patient_intake_service.get_intake_state(chat_session.id)
        prompt = approval_prompt(intake_state)
        deliver_reply(telegram_client, patient_ph_no, prompt)
        return prompt

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

    previous_items = await chat_history_service.get_agent_items(chat_session.id)
    if not previous_items and previous_messages:
        # Session predates agent item storage: seed it from the text transcript
        previous_items = messages_to_agent_items(previous_messages)
        await chat_history_service.add_agent_items(chat_session.id, previous_items)

    system_prompt = get_system_prompt()
    user_item = {"role": "user", "content": patient_message}
    input_list = format_messages_for_runner(
        user_question=patient_message,
        previous_items=previous_items,
        system_prompt=system_prompt,
    )

    tool_context = await build_tool_context(
        patient, chat_session.id, appointment_service, patient_intake_service
    )

    response = await run_agent(agent, input_list, tool_context)

    return await finalize_run(
        response,
        tool_context,
        user_item,
        user_message.message_sequence,
        chat_history_service,
        pending_approval_service,
        telegram_client,
        patient_ph_no,
    )


async def handle_approval(
    callback_query: CallbackQuery,
    patient_service: PatientService,
    chat_history_service: ChatHistoryService,
    patient_intake_service: PatientIntakeService,
    pending_approval_service: PendingApprovalService,
    agent: Agent,
    telegram_client: TelegramClient,
    appointment_service: AppointmentService,
):
    """Resume a paused run with the patient's Go Ahead / Changes needed decision."""
    # Answer first: the agent run below can take long enough for the query to expire.
    acknowledge_button_press(telegram_client, callback_query.id)

    patient_ph_no = str(callback_query.from_user.id)
    session_id = session_id_for(patient_ph_no)

    decision = callback_query.data
    if decision not in (APPROVE, CHANGES_NEEDED):
        if not await pending_approval_service.get(session_id):
            return "There is nothing waiting for your approval."
        intake_state = await patient_intake_service.get_intake_state(session_id)
        prompt = approval_prompt(intake_state)
        deliver_reply(telegram_client, patient_ph_no, prompt)
        return prompt

    # Claiming deletes the row, so a repeated press finds nothing and cannot
    # resume the same run twice.
    pending = await pending_approval_service.claim(session_id)
    if not pending:
        return "There is nothing waiting for your approval."
    remove_buttons(telegram_client, callback_query)

    try:
        return await resume_approval(
            pending,
            decision,
            patient_ph_no,
            session_id,
            patient_service,
            chat_history_service,
            patient_intake_service,
            pending_approval_service,
            agent,
            telegram_client,
            appointment_service,
        )
    except Exception:
        # The decision wasn't applied: restore the prompt so it can be retried.
        await pending_approval_service.save(pending)
        raise


async def resume_approval(
    pending: PendingApproval,
    decision: str,
    patient_ph_no: str,
    session_id,
    patient_service: PatientService,
    chat_history_service: ChatHistoryService,
    patient_intake_service: PatientIntakeService,
    pending_approval_service: PendingApprovalService,
    agent: Agent,
    telegram_client: TelegramClient,
    appointment_service: AppointmentService,
):
    patient = await patient_service.get_patient_by_patient_ph_no(patient_ph_no)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    set_span_attributes(
        {"patient.id": str(patient.id), "chat_session.id": str(session_id)}
    )

    # The context isn't saved with the run state (services, UUIDs), so rebuild it.
    tool_context = await build_tool_context(
        patient, session_id, appointment_service, patient_intake_service
    )
    state = await RunState.from_string(
        agent,
        pending.run_state,
        context_override=RunContextWrapper(tool_context),
    )
    for interruption in state.get_interruptions():
        if decision == APPROVE:
            state.approve(interruption)
        else:
            state.reject(interruption, rejection_message=CHANGES_REJECTION_MESSAGE)

    response = await run_agent(agent, state)

    return await finalize_run(
        response,
        tool_context,
        pending.user_item,
        pending.user_message_sequence,
        chat_history_service,
        pending_approval_service,
        telegram_client,
        patient_ph_no,
    )


@router.post("/webhook")
async def telegram_webhook(
    update: TelegramWebhookUpdate,
    patient_service: Annotated[PatientService, Depends(get_patient_service)],
    chat_history_service: Annotated[
        ChatHistoryService, Depends(get_chat_history_service)
    ],
    patient_intake_service: Annotated[
        PatientIntakeService, Depends(get_patient_intake_service)
    ],
    pending_approval_service: Annotated[
        PendingApprovalService, Depends(get_pending_approval_service)
    ],
    agent: Annotated[Agent, Depends(get_agent)],
    telegram_client: Annotated[TelegramClient, Depends(get_telegram_client)],
    appointment_service: Annotated[
        AppointmentService, Depends(get_appointment_service)
    ],
):
    """Single Telegram entry point: a button press resumes a paused run, a message starts one."""
    if update.callback_query:
        return await handle_approval(
            update.callback_query,
            patient_service,
            chat_history_service,
            patient_intake_service,
            pending_approval_service,
            agent,
            telegram_client,
            appointment_service,
        )
    if update.message:
        return await handle_message(
            update.message,
            patient_service,
            chat_history_service,
            patient_intake_service,
            pending_approval_service,
            agent,
            telegram_client,
            appointment_service,
        )
    raise HTTPException(
        status_code=422, detail="Expected a message or a callback_query"
    )


# @router.get("/webhook")
# async def verify(
#     mode: str = Query(None, alias="hub.mode"),
#     token: str = Query(None, alias="hub.verify_token"),
#     challenge: str = Query(None, alias="hub.challenge"),
# ):
#     if mode and token:
#         if mode == "subscribe" and token == VERIFY_TOKEN:  # however you load config
#             # logging.info("WEBHOOK_VERIFIED")
#             return PlainTextResponse(content=challenge, status_code=200)
#         else:
#             # logging.info("VERIFICATION_FAILED")
#             raise HTTPException(status_code=403, detail="Verification failed")
#     else:
#         # logging.info("MISSING_PARAMETER")
#         raise HTTPException(status_code=400, detail="Missing parameters")
