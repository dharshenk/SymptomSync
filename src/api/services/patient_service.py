# api/services/patient_service.py
from api.clients.postgres_sql_client import PostgresSQLClient
from api.models.patient_model import Patient
from uuid import UUID
import logging


class PatientService:
    """CRUD operations for patients table using Pydantic model."""

    def __init__(self, postgres_client: PostgresSQLClient):
        self._postgres_client = postgres_client
        self._logger = logging.getLogger(__name__)

    async def create_patient(self, patient: Patient) -> Patient:
        """Insert a new patient record and return the created model."""
        insert_query = """
            INSERT INTO patients (
                patient_id,
                first_name,
                last_name,
                email,
                phone_number,
                date_of_birth,
                gender,
                emergency_contact_name,
                emergency_contact_phone,
                is_active
            )
            VALUES (
                %(patient_id)s,
                %(first_name)s,
                %(last_name)s,
                %(email)s,
                %(phone_number)s,
                %(date_of_birth)s,
                %(gender)s,
                %(emergency_contact_name)s,
                %(emergency_contact_phone)s,
                %(is_active)s
            )
            RETURNING *;
        """

        params = patient.model_dump()
        self._postgres_client.execute_command(insert_query, params)

        return patient

    async def get_patient(self, patient_id: UUID) -> Patient | None:
        """Fetch a patient by internal UUID."""
        select_query = "SELECT * FROM patients WHERE id = %(id)s;"
        rows = self._postgres_client.execute_query(
            select_query, {"id": str(patient_id)}, fetch="one"
        )

        if not rows:
            return None

        return Patient(**rows[0])

    async def get_patient_by_patient_id(self, patient_id: str) -> Patient | None:
        """Fetch a patient by human-readable ID like PAT-001."""
        select_query = "SELECT * FROM patients WHERE patient_id = %(patient_id)s;"
        rows = self._postgres_client.execute_query(
            select_query, {"patient_id": patient_id}, fetch="one"
        )

        if not rows:
            return None

        return Patient(**rows[0])

    async def update_patient(self, patient_id: UUID, updates: dict) -> Patient | None:
        """Update a patient record by UUID."""
        if not updates:
            return None

        set_clause = ", ".join([f"{k} = %({k})s" for k in updates.keys()])
        query = f"""
            UPDATE patients
            SET {set_clause}, updated_at = CURRENT_TIMESTAMP
            WHERE id = %(id)s
            RETURNING *;
        """

        params = {"id": str(patient_id), **updates}
        rows = self._postgres_client.execute_query(query, params, fetch="one")

        if not rows:
            return None

        return Patient(**rows[0])

    async def delete_patient(self, patient_id: UUID) -> bool:
        """Hard-delete a patient record."""
        query = "DELETE FROM patients WHERE id = %(id)s;"
        rowcount = self._postgres_client.execute_command(query, {"id": str(patient_id)})
        return rowcount > 0
