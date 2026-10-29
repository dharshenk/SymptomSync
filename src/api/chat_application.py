"""Application layer: one use case per Incoming Message, returning a Reply.

Knows the Patient, the Chat Session and the database services, but nothing
about the Channel: it never sends anything and imports no FastAPI types.
"""

from datetime import date
import os
import uuid

from src.api.agent_runtime import Finished, NeedsApproval, RunOutcome
from src.api.agent_tools import ToolContext
from src.api.conversation import resolve_conversation
from src.api.models.chat_model import Choice, Decision, IncomingMessage, Reply
from src.api.models.chat_session_model import ChatMessage, SenderType
from src.api.models.patient_intake_model import PatientIntakeState
from src.api.models.patient_model import Patient
from src.api.models.pending_approval_model import PendingApproval
from src.api.services.appointment_service import AppointmentService
from src.api.services.chat_history_service import ChatHistoryService
from src.api.services.patient_intake_service import PatientIntakeService
from src.api.services.patient_service import PatientService
from src.api.services.pending_approval_service import PendingApprovalService
from src.api.telemetry import set_span_attributes

STILL_WORKING = "Still working on your booking, one moment."


def get_doctor_id() -> uuid.UUID:
    doctor_id = os.getenv("DOCTOR_ID")
    if not doctor_id:
        raise RuntimeError("DOCTOR_ID is not set")
    return uuid.UUID(doctor_id)


def approval_prompt(intake_state: PatientIntakeState) -> Reply:
    """Booking summary with the Go Ahead / Changes needed choices."""
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
    return Reply(
        text=text,
        choices=[
            Choice(label="Go Ahead", decision=Decision.GO_AHEAD),
            Choice(label="Changes needed", decision=Decision.CHANGES_NEEDED),
        ],
    )


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


async def finalize_run(
    outcome: RunOutcome,
    tool_context: ToolContext,
    user_item: dict,
    user_message_sequence: int,
    chat_history_service: ChatHistoryService,
    pending_approval_service: PendingApprovalService,
) -> Reply:
    """Persist a finished run, or save a paused one until the patient decides."""
    chat_session_id = tool_context.chat_session_id

    if isinstance(outcome, NeedsApproval):
        await pending_approval_service.save(
            PendingApproval(
                chat_session_id=chat_session_id,
                run_state=outcome.state,
                user_item=user_item,
                user_message_sequence=user_message_sequence,
            )
        )
        return approval_prompt(tool_context.patient_intake_state)

    if not isinstance(outcome, Finished):
        raise TypeError(f"Unexpected run outcome: {outcome!r}")
    await chat_history_service.add_message(
        ChatMessage(
            session_id=chat_session_id,
            sender_type=SenderType.bot,
            message_content=outcome.text,
            message_sequence=user_message_sequence + 1,
        )
    )
    await chat_history_service.add_agent_items(
        chat_session_id, [user_item] + outcome.items
    )
    await pending_approval_service.delete(chat_session_id)
    return Reply(text=outcome.text)


# LEGACY: remove once no stored session predates agent item storage.
async def seed_agent_items_from_transcript(
    chat_history_service: ChatHistoryService,
    chat_session_id: uuid.UUID,
    previous_messages: list[ChatMessage],
) -> list[dict]:
    """Build (and store) agent items for a session that only has a text transcript."""
    sender_type_map = {"patient": "user", "bot": "assistant"}
    items = [
        {
            "role": sender_type_map.get(msg.sender_type.lower()),
            "content": msg.message_content,
        }
        for msg in previous_messages
    ]
    await chat_history_service.add_agent_items(chat_session_id, items)
    return items


class ChatApplication:
    """The chat use cases, independent of the Channel."""

    def __init__(
        self,
        patient_service: PatientService,
        chat_history_service: ChatHistoryService,
        patient_intake_service: PatientIntakeService,
        pending_approval_service: PendingApprovalService,
        appointment_service: AppointmentService,
        agent_runtime,
    ):
        self.patient_service = patient_service
        self.chat_history_service = chat_history_service
        self.patient_intake_service = patient_intake_service
        self.pending_approval_service = pending_approval_service
        self.appointment_service = appointment_service
        self.agent_runtime = agent_runtime

    async def handle_message(self, message: IncomingMessage) -> Reply:
        """Run the agent on a Patient's message and return what to say back."""
        patient, chat_session = await resolve_conversation(
            message.sender_id, self.patient_service, self.chat_history_service
        )
        set_span_attributes(
            {"patient.id": str(patient.id), "chat_session.id": str(chat_session.id)}
        )

        # A run is paused (or its decision is being applied): don't start another one.
        pending = await self.pending_approval_service.get(chat_session.id)
        if pending and pending.status == "processing":
            return Reply(text=STILL_WORKING)
        if pending:
            intake_state = await self.patient_intake_service.get_intake_state(
                chat_session.id
            )
            return approval_prompt(intake_state)

        previous_messages = await self.chat_history_service.get_session_messages(
            session_id=chat_session.id
        )
        user_message = ChatMessage(
            session_id=chat_session.id,
            sender_type=SenderType.patient,
            message_content=message.text,
            message_sequence=(
                previous_messages[-1].message_sequence + 1 if previous_messages else 1
            ),
        )
        await self.chat_history_service.add_message(user_message)

        previous_items = await self.chat_history_service.get_agent_items(
            chat_session.id
        )
        if not previous_items and previous_messages:
            previous_items = await seed_agent_items_from_transcript(
                self.chat_history_service, chat_session.id, previous_messages
            )

        tool_context = await build_tool_context(
            patient,
            chat_session.id,
            self.appointment_service,
            self.patient_intake_service,
        )
        outcome = await self.agent_runtime.run(
            previous_items, message.text, tool_context
        )
        return await finalize_run(
            outcome,
            tool_context,
            {"role": "user", "content": message.text},
            user_message.message_sequence,
            self.chat_history_service,
            self.pending_approval_service,
        )
