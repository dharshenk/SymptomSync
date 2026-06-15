# api/services/patient_service.py
from src.api.clients.postgres_sql_client import PostgresSQLClient
from src.api.models.patient_model import Patient
from uuid import UUID
import logging
import json


class PatientService:
    """CRUD operations for patients table using Pydantic model."""

    def __init__(self, postgres_client: PostgresSQLClient):
        self._postgres_client = postgres_client
        self._logger = logging.getLogger(__name__)

    async def create_patient(self, patient: Patient) -> Patient:
        """Insert a new patient record.

        Returns:
            True if the patient was created successfully, False if no row was affected.

        Raises:
            DatabaseError: Re-raised from the postgres client on query failure.
        """
        insert_query = """
            INSERT INTO patients (
                id,
                patient_ph_no,
                first_name,
                last_name,
                email,
                date_of_birth,
                gender,
                emergency_contact_name,
                emergency_contact_phone,
                is_active
            )
            VALUES (
                %(id)s,
                %(patient_ph_no)s,
                %(first_name)s,
                %(last_name)s,
                %(email)s,
                %(date_of_birth)s,
                %(gender)s,
                %(emergency_contact_name)s,
                %(emergency_contact_phone)s,
                %(is_active)s
            );
        """

        try:
            params = json.loads(patient.model_dump_json())
            self._postgres_client.execute_command(insert_query, params)
            return patient
        except Exception as e:
            self._logger.error(f"Error creating patient: {str(e)}")
            raise

    async def get_patient(self, patient_id: UUID) -> Patient | None:
        """Fetch a patient by internal UUID."""
        select_query = "SELECT * FROM patients WHERE id = %(id)s;"
        rows = self._postgres_client.execute_query(
            select_query, {"id": str(patient_id)}, fetch="one"
        )

        if not rows:
            return None

        return Patient(**rows[0])

    async def get_patient_by_patient_ph_no(self, patient_ph_no: str) -> Patient | None:
        """Fetch a patient by phone number using the patient_ph_no field."""
        select_query = "SELECT * FROM patients WHERE patient_ph_no = %(patient_ph_no)s;"
        rows = self._postgres_client.execute_query(
            select_query, {"patient_ph_no": patient_ph_no}, fetch="one"
        )

        if not rows:
            return None

        return Patient(**rows[0])

    async def update_patient(self, patient_id: UUID, updates: dict) -> bool:
        """Update a patient record by UUID.

        Returns:
            True if the patient was updated, False if no updates provided or ID not found.

        Raises:
            DatabaseError: Re-raised from the postgres client on query failure.
        """
        if not updates:
            return False

        set_clause = ", ".join([f"{k} = %({k})s" for k in updates.keys()])
        query = f"""
            UPDATE patients
            SET {set_clause}, updated_at = CURRENT_TIMESTAMP
            WHERE id = %(id)s;
        """

        try:
            params = {"id": str(patient_id), **updates}
            rowcount = self._postgres_client.execute_command(query, params)
            if rowcount == 0:
                self._logger.warning(f"Patient {patient_id} not found for update")
                return False
            return True
        except Exception as e:
            self._logger.error(f"Error updating patient: {str(e)}")
            raise

    async def delete_patient(self, patient_id: UUID) -> bool:
        """Hard-delete a patient record.

        Returns:
            True if the patient was deleted, False if the ID was not found.

        Raises:
            DatabaseError: Re-raised from the postgres client on query failure.
        """
        try:
            query = "DELETE FROM patients WHERE id = %(id)s;"
            rowcount = self._postgres_client.execute_command(
                query, {"id": str(patient_id)}
            )
            if rowcount == 0:
                self._logger.warning(f"Patient {patient_id} not found for deletion")
                return False
            self._logger.info(f"Patient {patient_id} deleted successfully")
            return True
        except Exception as e:
            self._logger.error(f"Error deleting patient: {str(e)}")
            raise
