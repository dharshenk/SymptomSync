import uuid
from typing import NamedTuple

from src.api.models.chat_session_model import ChatSession
from src.api.models.patient_model import Patient
from src.api.services.chat_history_service import ChatHistoryService
from src.api.services.patient_service import PatientService


class Conversation(NamedTuple):
    """The Patient and Chat Session a Sender ID belongs to."""

    patient: Patient
    chat_session: ChatSession


def session_id_for(sender_id: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, sender_id)


async def resolve_conversation(
    sender_id: str,
    patient_service: PatientService,
    chat_history_service: ChatHistoryService,
) -> Conversation:
    """Get or create the Patient and Chat Session for a Sender ID."""
    patient = await patient_service.get_patient_by_patient_ph_no(sender_id)
    if not patient:
        patient = await patient_service.create_patient(Patient(patient_ph_no=sender_id))

    session_id = session_id_for(sender_id)
    chat_session = await chat_history_service.get_session(session_id)
    if not chat_session:
        chat_session = await chat_history_service.create_session(session_id, patient.id)

    return Conversation(patient=patient, chat_session=chat_session)
