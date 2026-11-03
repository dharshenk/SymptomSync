from src.api.telemetry import trace_db_operation
import json
from typing import Any
from src.api.clients.postgres_sql_client import PostgresSQLClient
from src.api.models.chat_session_model import ChatSession, ChatMessage, SessionStatus
from uuid import UUID


class ChatHistoryService:

    def __init__(self, postgres_client: PostgresSQLClient):
        self._postgres_client = postgres_client

    @trace_db_operation("chat_history.create_session")
    async def create_session(self, session_id: UUID, patient_id: UUID) -> ChatSession:
        chat_session = ChatSession(id=session_id, patient_id=patient_id)
        insert_query = """
            INSERT INTO chat_sessions (
                id,
                patient_id
            )
            VALUES (
                %(id)s,
                %(patient_id)s
            )
            RETURNING id;
        """

        params = {
            "id": str(session_id),
            "patient_id": str(patient_id),
        }
        self._postgres_client.execute_command(query=insert_query, params=params)
        return chat_session

    @trace_db_operation("chat_history.get_session")
    async def get_session(self, session_id: UUID) -> ChatSession | None:
        select_query = """
            SELECT
                id,
                patient_id,
                session_status,
                started_at,
                completed_at,
                total_messages,
                session_summary,
                appointment_requested,
                created_at
            FROM chat_sessions
            WHERE id = %(id)s;
        """

        params = {"id": str(session_id)}
        rows = self._postgres_client.execute_query(
            query=select_query, params=params, fetch="one"
        )
        if not rows:
            return None

        row = rows[0]
        chat_session = ChatSession(
            id=row["id"],
            patient_id=row["patient_id"],
            session_status=row["session_status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            total_messages=row["total_messages"],
            session_summary=row["session_summary"],
            appointment_requested=row["appointment_requested"],
            created_at=row["created_at"],
        )
        return chat_session

    @trace_db_operation("chat_history.get_current_session")
    async def get_current_session(self, patient_id: UUID) -> ChatSession | None:
        """The Patient's newest active Chat Session, or None."""
        select_query = """
            SELECT id FROM chat_sessions
            WHERE patient_id = %(patient_id)s AND session_status = 'active'
            ORDER BY started_at DESC, created_at DESC
            LIMIT 1;
        """
        rows = self._postgres_client.execute_query(
            query=select_query, params={"patient_id": str(patient_id)}, fetch="one"
        )
        if not rows:
            return None
        return await self.get_session(rows[0]["id"])

    @trace_db_operation("chat_history.close_session")
    async def close_session(self, session_id: UUID, status: SessionStatus) -> None:
        """Mark a Chat Session `completed` or `abandoned`."""
        self._postgres_client.execute_command(
            query="""
                UPDATE chat_sessions
                SET session_status = %(status)s, completed_at = NOW()
                WHERE id = %(id)s;
            """,
            params={"id": str(session_id), "status": SessionStatus(status).value},
        )

    @trace_db_operation("chat_history.replace_session")
    async def replace_session(
        self,
        old_session_id: UUID,
        new_session_id: UUID,
        patient_id: UUID,
        status: SessionStatus,
    ) -> ChatSession:
        """Close the old session and create a fresh one with blank intake atomically.

        Pending approval deletion belongs to the same transaction, so a failed
        replacement leaves the old session usable. execute_command commits this
        entire SQL batch once and rolls it back if any statement fails.
        """
        new_session = ChatSession(id=new_session_id, patient_id=patient_id)
        self._postgres_client.execute_command(
            query="""
                DELETE FROM pending_approvals
                WHERE chat_session_id = %(old_session_id)s;

                UPDATE chat_sessions
                SET session_status = %(status)s, completed_at = NOW()
                WHERE id = %(old_session_id)s;

                INSERT INTO chat_sessions (id, patient_id)
                VALUES (%(new_session_id)s, %(patient_id)s);

                INSERT INTO patient_intake_state (chat_session_id)
                VALUES (%(new_session_id)s);
            """,
            params={
                "old_session_id": str(old_session_id),
                "new_session_id": str(new_session_id),
                "patient_id": str(patient_id),
                "status": SessionStatus(status).value,
            },
        )
        return new_session

    @trace_db_operation("chat_history.add_message")
    async def add_message(self, chat_message: ChatMessage) -> None:
        insert_query = """
            INSERT INTO chat_messages (
                session_id,
                message_sequence,
                sender_type,
                message_content,
                message_type
            )
            VALUES (
                %(session_id)s,
                %(message_sequence)s,
                %(sender_type)s,
                %(message_content)s,
                %(message_type)s
            );
        """

        params = {
            "session_id": str(chat_message.session_id),
            "message_sequence": chat_message.message_sequence,
            "sender_type": chat_message.sender_type,
            "message_content": chat_message.message_content,
            "message_type": chat_message.message_type,
        }
        self._postgres_client.execute_command(query=insert_query, params=params)
        return

    @trace_db_operation("chat_history.get_session_messages")
    async def get_session_messages(self, session_id: UUID) -> list[ChatMessage] | None:
        select_query = """
            SELECT
                id,
                session_id,
                message_sequence,
                sender_type,
                message_content,
                message_type
            FROM chat_messages
            WHERE session_id = %(session_id)s
            ORDER BY message_sequence ASC;
        """

        params = {"session_id": str(session_id)}
        rows = self._postgres_client.execute_query(
            query=select_query, params=params, fetch="all"
        )
        if not rows:
            return None

        messages = [
            ChatMessage(
                session_id=row["session_id"],
                message_sequence=row["message_sequence"],
                sender_type=row["sender_type"],
                message_content=row["message_content"],
                message_type=row["message_type"],
            )
            for row in rows
        ]
        return messages

    @trace_db_operation("chat_history.get_agent_items")
    async def get_agent_items(self, session_id: UUID) -> list[dict[str, Any]]:
        select_query = """
            SELECT item::text AS item
            FROM chat_agent_items
            WHERE session_id = %(session_id)s
            ORDER BY item_sequence ASC;
        """

        params = {"session_id": str(session_id)}
        rows = self._postgres_client.execute_query(
            query=select_query, params=params, fetch="all"
        )
        return [json.loads(row["item"]) for row in rows or []]

    @trace_db_operation("chat_history.add_agent_items")
    async def add_agent_items(
        self, session_id: UUID, items: list[dict[str, Any]]
    ) -> None:
        if not items:
            return

        next_sequence_query = """
            SELECT COALESCE(MAX(item_sequence), 0) + 1 AS next_sequence
            FROM chat_agent_items
            WHERE session_id = %(session_id)s;
        """
        rows = self._postgres_client.execute_query(
            query=next_sequence_query,
            params={"session_id": str(session_id)},
            fetch="one",
        )
        start_sequence = rows[0]["next_sequence"]

        insert_query = """
            INSERT INTO chat_agent_items (
                session_id,
                item_sequence,
                item
            )
            VALUES (
                %(session_id)s,
                %(item_sequence)s,
                %(item)s
            );
        """

        params_list = [
            {
                "session_id": str(session_id),
                "item_sequence": start_sequence + offset,
                "item": json.dumps(item),
            }
            for offset, item in enumerate(items)
        ]
        self._postgres_client.execute_many(query=insert_query, params_list=params_list)
        return
