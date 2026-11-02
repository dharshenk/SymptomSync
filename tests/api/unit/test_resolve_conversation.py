"""resolve_conversation: Sender ID -> Patient and Chat Session, get-or-create."""

import uuid
from types import SimpleNamespace

from src.api.conversation import resolve_conversation, session_id_for


class FakePatientService:
    def __init__(self, patients=None):
        self.by_sender = dict(patients or {})
        self.created = []

    async def get_patient_by_patient_ph_no(self, sender_id):
        return self.by_sender.get(sender_id)

    async def create_patient(self, patient):
        self.created.append(patient)
        self.by_sender[patient.patient_ph_no] = patient
        return patient


class FakeChatHistoryService:
    def __init__(self, sessions=None):
        self.sessions = dict(sessions or {})
        self.created = []

    async def get_session(self, session_id):
        return self.sessions.get(session_id)

    async def create_session(self, session_id, patient_id):
        session = SimpleNamespace(id=session_id, patient_id=patient_id)
        self.created.append(session)
        self.sessions[session_id] = session
        return session


async def test_new_sender_gets_a_patient_and_a_chat_session():
    patients, history = FakePatientService(), FakeChatHistoryService()

    conversation = await resolve_conversation("42", patients, history)

    assert conversation.patient.patient_ph_no == "42"
    assert conversation.chat_session.id == session_id_for("42")
    assert conversation.chat_session.patient_id == conversation.patient.id


async def test_known_sender_is_reused_not_recreated():
    patients, history = FakePatientService(), FakeChatHistoryService()
    first = await resolve_conversation("42", patients, history)

    second = await resolve_conversation("42", patients, history)

    assert second.patient.id == first.patient.id
    assert second.chat_session.id == first.chat_session.id
    assert len(patients.created) == 1 and len(history.created) == 1


async def test_existing_patient_without_session_only_gets_a_session():
    patients, history = FakePatientService(), FakeChatHistoryService()
    await patients.create_patient(SimpleNamespace(id=uuid.uuid4(), patient_ph_no="7"))
    patients.created.clear()

    conversation = await resolve_conversation("7", patients, history)

    assert patients.created == []
    assert conversation.chat_session.patient_id == conversation.patient.id


def test_chat_session_id_is_stable_per_sender():
    assert session_id_for("42") == session_id_for("42")
    assert session_id_for("42") != session_id_for("43")
