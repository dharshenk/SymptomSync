from datetime import date
import os
import uuid

from agents import Agent, RunState, Runner
from dotenv import load_dotenv
from jinja2 import Template

from src.api.agent_tools import ToolContext
from src.api.models.chat_session_model import ChatMessage
from src.api.models.patient_intake_model import PatientIntakeState
from src.api.models.patient_model import Patient
from src.api.services.appointment_service import AppointmentService
from src.api.services.patient_intake_service import PatientIntakeService
from src.api.telemetry import traced

load_dotenv()

SYSTEM_PROMPT_PATH = os.getenv("SYSTEM_PROMPT_PATH")


def get_doctor_id() -> uuid.UUID:
    doctor_id = os.getenv("DOCTOR_ID")
    if not doctor_id:
        raise RuntimeError("DOCTOR_ID is not set")
    return uuid.UUID(doctor_id)


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
        doctor_id=get_doctor_id(),
        appointment=latest_appointment,
        appointment_date=(
            latest_appointment.appointment_date if latest_appointment else date.today()
        ),
    )
