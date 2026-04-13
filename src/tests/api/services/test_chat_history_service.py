"""Integration tests for ChatHistoryService."""

import pytest
from uuid import uuid4

from api.clients.postgres_sql_client import PostgresSQLClient
from api.services.chat_history_service import ChatHistoryService
from api.models.chat_session_model import (
    ChatSession,
    ChatMessage,
    SenderType,
    MessageType,
)
from api.models.patient_model import Patient


# ============================================
# UNIT TESTS (no DB required)
# ============================================


class TestChatModelValidation:
    """Pure unit tests for ChatSession / ChatMessage model constraints."""

    def test_chat_session_defaults(self):
        session = ChatSession(patient_id=uuid4())
        assert session.session_status == "active"
        assert session.total_messages == 0
        assert session.appointment_requested is False
        assert session.completed_at is None

    def test_chat_message_requires_content(self):
        """Empty message_content should raise a validation error."""
        with pytest.raises(Exception):
            ChatMessage(
                session_id=uuid4(),
                message_sequence=1,
                sender_type=SenderType.patient,
                message_content="",
            )

    def test_chat_message_whitespace_only_raises(self):
        with pytest.raises(Exception):
            ChatMessage(
                session_id=uuid4(),
                message_sequence=1,
                sender_type=SenderType.patient,
                message_content="   ",
            )

    def test_chat_message_defaults(self):
        msg = ChatMessage(
            session_id=uuid4(),
            message_sequence=1,
            sender_type=SenderType.bot,
            message_content="Hello",
        )
        assert msg.message_type == "text"
        assert msg.metadata is None


# ============================================
# INTEGRATION TESTS
# ============================================


@pytest.mark.integration
class TestChatHistoryServiceCreateSession:
    """Tests for creating chat sessions."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, db_client: PostgresSQLClient):
        self._session_ids: list[str] = []
        yield
        for sid in self._session_ids:
            db_client.execute_command(
                "DELETE FROM chat_sessions WHERE id = %(id)s;", {"id": sid}
            )

    async def test_create_session_returns_chat_session(
        self,
        chat_history_service: ChatHistoryService,
        sample_patient: Patient,
    ):
        session_id = uuid4()
        self._session_ids.append(str(session_id))

        result = await chat_history_service.create_session(
            session_id, sample_patient.id
        )

        assert isinstance(result, ChatSession)
        assert result.id == session_id
        assert result.patient_id == sample_patient.id

    async def test_create_session_persists_in_db(
        self,
        chat_history_service: ChatHistoryService,
        sample_patient: Patient,
    ):
        session_id = uuid4()
        self._session_ids.append(str(session_id))

        await chat_history_service.create_session(session_id, sample_patient.id)
        fetched = await chat_history_service.get_session(session_id)

        assert fetched is not None
        assert fetched.id == session_id
        assert fetched.session_status == "active"


@pytest.mark.integration
class TestChatHistoryServiceGetSession:
    """Tests for retrieving chat sessions."""

    @pytest.fixture()
    def chat_session(
        self,
        db_client: PostgresSQLClient,
        sample_patient: Patient,
    ):
        session_id = uuid4()
        db_client.execute_command(
            """
            INSERT INTO chat_sessions (id, patient_id)
            VALUES (%(id)s, %(patient_id)s);
            """,
            {"id": str(session_id), "patient_id": str(sample_patient.id)},
        )
        yield session_id
        db_client.execute_command(
            "DELETE FROM chat_sessions WHERE id = %(id)s;", {"id": str(session_id)}
        )

    async def test_get_existing_session(
        self,
        chat_history_service: ChatHistoryService,
        chat_session,
    ):
        fetched = await chat_history_service.get_session(chat_session)
        assert fetched is not None
        assert fetched.id == chat_session

    async def test_get_nonexistent_session(
        self, chat_history_service: ChatHistoryService
    ):
        result = await chat_history_service.get_session(uuid4())
        assert result is None


@pytest.mark.integration
class TestChatHistoryServiceMessages:
    """Tests for adding and retrieving messages."""

    @pytest.fixture()
    def chat_session(
        self,
        db_client: PostgresSQLClient,
        sample_patient: Patient,
    ):
        """Create a session to attach messages to."""
        session_id = uuid4()
        db_client.execute_command(
            """
            INSERT INTO chat_sessions (id, patient_id)
            VALUES (%(id)s, %(patient_id)s);
            """,
            {"id": str(session_id), "patient_id": str(sample_patient.id)},
        )
        yield session_id
        # Cascade takes care of messages when session is deleted
        db_client.execute_command(
            "DELETE FROM chat_sessions WHERE id = %(id)s;", {"id": str(session_id)}
        )

    async def test_add_and_retrieve_single_message(
        self,
        chat_history_service: ChatHistoryService,
        chat_session,
    ):
        msg = ChatMessage(
            session_id=chat_session,
            message_sequence=1,
            sender_type=SenderType.patient,
            message_content="I have a headache",
        )
        await chat_history_service.add_message(msg)

        messages = await chat_history_service.get_session_messages(chat_session)
        assert messages is not None
        assert len(messages) == 1
        assert messages[0].message_content == "I have a headache"
        assert messages[0].sender_type == "patient"

    async def test_add_multiple_messages_in_order(
        self,
        chat_history_service: ChatHistoryService,
        chat_session,
    ):
        msgs = [
            ChatMessage(
                session_id=chat_session,
                message_sequence=1,
                sender_type=SenderType.patient,
                message_content="Hello",
            ),
            ChatMessage(
                session_id=chat_session,
                message_sequence=2,
                sender_type=SenderType.bot,
                message_content="How can I help?",
            ),
            ChatMessage(
                session_id=chat_session,
                message_sequence=3,
                sender_type=SenderType.patient,
                message_content="I feel dizzy",
            ),
        ]
        for m in msgs:
            await chat_history_service.add_message(m)

        messages = await chat_history_service.get_session_messages(chat_session)
        assert messages is not None
        assert len(messages) == 3
        # Verify ordering
        assert messages[0].message_sequence == 1
        assert messages[1].message_sequence == 2
        assert messages[2].message_sequence == 3

    async def test_get_messages_for_empty_session(
        self,
        chat_history_service: ChatHistoryService,
        chat_session,
    ):
        """Session with no messages returns None."""
        result = await chat_history_service.get_session_messages(chat_session)
        assert result is None

    async def test_duplicate_sequence_raises(
        self,
        chat_history_service: ChatHistoryService,
        chat_session,
    ):
        """Duplicate (session_id, message_sequence) violates UNIQUE constraint."""
        msg1 = ChatMessage(
            session_id=chat_session,
            message_sequence=1,
            sender_type=SenderType.patient,
            message_content="First",
        )
        msg2 = ChatMessage(
            session_id=chat_session,
            message_sequence=1,  # same sequence
            sender_type=SenderType.bot,
            message_content="Duplicate seq",
        )
        await chat_history_service.add_message(msg1)
        with pytest.raises(Exception):
            await chat_history_service.add_message(msg2)

    async def test_message_with_different_types(
        self,
        chat_history_service: ChatHistoryService,
        chat_session,
    ):
        msg = ChatMessage(
            session_id=chat_session,
            message_sequence=1,
            sender_type=SenderType.patient,
            message_content="Photo of rash",
            message_type=MessageType.image,
        )
        await chat_history_service.add_message(msg)

        messages = await chat_history_service.get_session_messages(chat_session)
        assert messages is not None
        assert messages[0].message_type == "image"
