"""CRUD operations for the current intake state of a chat session."""

from typing import Any
from uuid import UUID

from src.api.clients.postgres_sql_client import PostgresSQLClient
from src.api.models.patient_intake_model import PatientIntakeState, PatientIntakeUpdate

# Select supported fields so older database columns do not enter the model.
_COLUMNS = ", ".join(PatientIntakeState.model_fields)


class PatientIntakeService:
    """Store intake details incrementally, addressing records by chat session ID."""

    def __init__(self, postgres_client: PostgresSQLClient):
        self._postgres_client = postgres_client

    async def create_intake_state(
        self, intake_state: PatientIntakeState
    ) -> PatientIntakeState:
        """Insert a state; duplicate sessions raise a database error."""
        params = intake_state.model_dump(mode="json")
        columns = ", ".join(params)
        placeholders = ", ".join(f"%({column})s" for column in params)
        self._postgres_client.execute_command(
            f"INSERT INTO patient_intake_state ({columns}) VALUES ({placeholders});",
            params,
        )
        return intake_state

    async def get_intake_state(
        self, chat_session_id: UUID
    ) -> PatientIntakeState | None:
        """Fetch a session's intake state, or None if it has not been created."""
        rows = self._postgres_client.execute_query(
            f"SELECT {_COLUMNS} FROM patient_intake_state WHERE chat_session_id = %(chat_session_id)s;",
            {"chat_session_id": str(chat_session_id)},
            fetch="one",
        )
        return PatientIntakeState(**rows[0]) if rows else None

    async def update_intake_state(
        self, chat_session_id: UUID, **fields: Any
    ) -> PatientIntakeState | None:
        """Replace only supplied fields, preserving all other collected details.

        For example: update_intake_state(session_id, age=32, symptoms="Headache").
        Pass None to clear a nullable field. Unknown fields and invalid values
        raise pydantic.ValidationError. IDs and creation timestamps cannot change.
        Returns the updated state, or None when no fields are supplied or the
        session has no state.
        """
        updates = PatientIntakeUpdate(**fields).model_dump(
            mode="json", exclude_unset=True
        )
        if not updates:
            return None

        # Field names come exclusively from the validated update schema.
        set_clause = ", ".join(f"{field} = %({field})s" for field in updates)
        rows = self._postgres_client.execute_query(
            f"""
            UPDATE patient_intake_state
            SET {set_clause}, updated_at = CURRENT_TIMESTAMP
            WHERE chat_session_id = %(chat_session_id)s
            RETURNING {_COLUMNS};
            """,
            {**updates, "chat_session_id": str(chat_session_id)},
            fetch="one",
            commit=True,
        )
        return PatientIntakeState(**rows[0]) if rows else None

    async def delete_intake_state(self, chat_session_id: UUID) -> bool:
        """Delete a session's state, returning False if no record exists."""
        rowcount = self._postgres_client.execute_command(
            "DELETE FROM patient_intake_state WHERE chat_session_id = %(chat_session_id)s;",
            {"chat_session_id": str(chat_session_id)},
        )
        return rowcount > 0
