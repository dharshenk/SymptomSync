import json
from uuid import UUID

from src.api.clients.postgres_sql_client import PostgresSQLClient
from src.api.models.pending_approval_model import PendingApproval


class PendingApprovalService:

    def __init__(self, postgres_client: PostgresSQLClient):
        self._postgres_client = postgres_client

    async def save(self, pending_approval: PendingApproval) -> None:
        upsert_query = """
            INSERT INTO pending_approvals (
                chat_session_id,
                run_state,
                user_item,
                user_message_sequence
            )
            VALUES (
                %(chat_session_id)s,
                %(run_state)s,
                %(user_item)s,
                %(user_message_sequence)s
            )
            ON CONFLICT (chat_session_id) DO UPDATE SET
                run_state = EXCLUDED.run_state,
                user_item = EXCLUDED.user_item,
                user_message_sequence = EXCLUDED.user_message_sequence,
                created_at = CURRENT_TIMESTAMP;
        """

        params = {
            "chat_session_id": str(pending_approval.chat_session_id),
            "run_state": pending_approval.run_state,
            "user_item": json.dumps(pending_approval.user_item),
            "user_message_sequence": pending_approval.user_message_sequence,
        }
        self._postgres_client.execute_command(query=upsert_query, params=params)

    async def get(self, chat_session_id: UUID) -> PendingApproval | None:
        select_query = """
            SELECT
                chat_session_id,
                run_state,
                user_item::text AS user_item,
                user_message_sequence
            FROM pending_approvals
            WHERE chat_session_id = %(chat_session_id)s;
        """

        params = {"chat_session_id": str(chat_session_id)}
        rows = self._postgres_client.execute_query(
            query=select_query, params=params, fetch="one"
        )
        if not rows:
            return None

        row = rows[0]
        return PendingApproval(
            chat_session_id=row["chat_session_id"],
            run_state=row["run_state"],
            user_item=json.loads(row["user_item"]),
            user_message_sequence=row["user_message_sequence"],
        )

    async def delete(self, chat_session_id: UUID) -> None:
        delete_query = """
            DELETE FROM pending_approvals
            WHERE chat_session_id = %(chat_session_id)s;
        """
        self._postgres_client.execute_command(
            query=delete_query, params={"chat_session_id": str(chat_session_id)}
        )
