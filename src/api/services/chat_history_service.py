import json
from typing import Any
from src.api.clients.postgres_sql_client import PostgresSQLClient
from src.api.models.chat_session_model import ChatSession, ChatMessage
from uuid import UUID


class ChatHistoryService:

    def __init__(self, postgres_client: PostgresSQLClient):
        self._postgres_client = postgres_client

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
