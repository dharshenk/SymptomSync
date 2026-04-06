# api/services/doctor_service.py
from api.clients.postgres_sql_client import PostgresSQLClient
from api.models.doctor_model import Doctor
from uuid import UUID
import logging
import json


class DoctorService:
    """CRUD operations for doctors table using Pydantic model."""

    def __init__(self, postgres_client: PostgresSQLClient):
        self._postgres_client = postgres_client
        self._logger = logging.getLogger(__name__)

    async def create_doctor(self, doctor: Doctor) -> Doctor | None:
        """
        Insert a new doctor record and return the created model.

        Args:
            doctor: Doctor model with required fields

        Returns:
            Created Doctor model or None if failed
        """
        insert_query = """
            INSERT INTO doctors (
                id,
                first_name,
                last_name,
                email,
                phone_number,
                license_number,
                specialization,
                years_experience,
                qualification,
                hospital_affiliation,
                consultation_fee,
                consultation_duration,
                bio,
                is_active
            )
            VALUES (
                %(id)s,
                %(first_name)s,
                %(last_name)s,
                %(email)s,
                %(phone_number)s,
                %(license_number)s,
                %(specialization)s,
                %(years_experience)s,
                %(qualification)s,
                %(hospital_affiliation)s,
                %(consultation_fee)s,
                %(consultation_duration)s,
                %(bio)s,
                %(is_active)s
            )
            RETURNING *;
        """

        params = json.loads(doctor.model_dump_json())
        params["id"] = str(params["id"])

        try:
            rows = self._postgres_client.execute_query(
                insert_query, params, fetch="one"
            )
            if not rows:
                self._logger.error("Failed to insert doctor")
                return None
            return Doctor(**rows[0])
        except Exception as e:
            self._logger.error(f"Error creating doctor: {str(e)}")
            return None

    async def get_doctor(self, doctor_id: UUID) -> Doctor | None:
        """
        Fetch a doctor by internal UUID.

        Args:
            doctor_id: UUID of the doctor

        Returns:
            Doctor model or None if not found
        """
        select_query = "SELECT * FROM doctors WHERE id = %(id)s;"
        rows = self._postgres_client.execute_query(
            select_query, {"id": str(doctor_id)}, fetch="one"
        )

        if not rows:
            return None

        return Doctor(**rows[0])

    async def get_doctor_by_license(self, license_number: str) -> Doctor | None:
        """
        Fetch a doctor by license number.

        Args:
            license_number: Doctor's license number

        Returns:
            Doctor model or None if not found
        """
        select_query = (
            "SELECT * FROM doctors WHERE license_number = %(license_number)s;"
        )
        rows = self._postgres_client.execute_query(
            select_query, {"license_number": license_number}, fetch="one"
        )

        if not rows:
            return None

        return Doctor(**rows[0])

    async def update_doctor(self, doctor_id: UUID, updates: dict) -> Doctor | None:
        """
        Update doctor record with provided fields.

        Args:
            doctor_id: UUID of the doctor to update
            updates: Dictionary of fields to update

        Returns:
            Updated Doctor model or None if failed
        """
        if not updates:
            self._logger.warning("No updates provided")
            return None

        # Build dynamic SET clause
        set_clauses = [f"{k} = %({k})s" for k in updates.keys()]
        set_clause = ", ".join(set_clauses)

        update_query = f"""
            UPDATE doctors
            SET {set_clause},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(doctor_id)s
            RETURNING *;
        """

        params = {**updates, "doctor_id": str(doctor_id)}

        try:
            rows = self._postgres_client.execute_query(
                update_query, params, fetch="one"
            )
            if not rows:
                self._logger.warning(f"Doctor {doctor_id} not found")
                return None
            return Doctor(**rows[0])
        except Exception as e:
            self._logger.error(f"Error updating doctor: {str(e)}")
            return None

    async def delete_doctor(self, doctor_id: UUID) -> bool:
        """
        Delete a doctor by ID (hard delete).

        Args:
            doctor_id: UUID of the doctor to delete

        Returns:
            True if successful, False otherwise
        """
        delete_query = "DELETE FROM doctors WHERE id = %(doctor_id)s;"
        params = {"doctor_id": str(doctor_id)}

        try:
            rowcount = self._postgres_client.execute_command(delete_query, params)
            if rowcount > 0:
                self._logger.info(f"Doctor {doctor_id} deleted successfully")
                return True
            else:
                self._logger.warning(f"Doctor {doctor_id} not found")
                return False
        except Exception as e:
            self._logger.error(f"Error deleting doctor: {str(e)}")
            return False

    async def deactivate_doctor(self, doctor_id: UUID) -> Doctor | None:
        """
        Deactivate a doctor by setting is_active to False (soft delete).

        Args:
            doctor_id: UUID of the doctor to deactivate

        Returns:
            Updated Doctor model or None if failed
        """
        update_query = """
            UPDATE doctors
            SET is_active = FALSE,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(doctor_id)s
            RETURNING *;
        """
        params = {"doctor_id": str(doctor_id)}

        try:
            rows = self._postgres_client.execute_query(
                update_query, params, fetch="one"
            )
            if not rows:
                self._logger.warning(f"Doctor {doctor_id} not found")
                return None
            self._logger.info(f"Doctor {doctor_id} deactivated")
            return Doctor(**rows[0])
        except Exception as e:
            self._logger.error(f"Error deactivating doctor: {str(e)}")
            return None

    async def list_doctors(
        self,
        specialization: str | None = None,
        is_active: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Doctor] | None:
        """
        Fetch doctors with optional filtering by specialization.

        Args:
            specialization: Optional specialization filter
            is_active: Filter by active status (default True)
            limit: Number of records to fetch
            offset: Offset from start

        Returns:
            List of Doctor models or None if error
        """
        query = "SELECT * FROM doctors WHERE is_active = %(is_active)s"
        params = {"is_active": is_active, "limit": limit, "offset": offset}

        if specialization:
            query += " AND specialization = %(specialization)s"
            params["specialization"] = specialization

        query += " ORDER BY created_at DESC LIMIT %(limit)s OFFSET %(offset)s;"

        try:
            rows = self._postgres_client.execute_query(query, params, fetch="all")
            if not rows:
                return []
            return [Doctor(**row) for row in rows]
        except Exception as e:
            self._logger.error(f"Error listing doctors: {str(e)}")
            return None

    async def get_doctors_by_specialization(
        self, specialization: str, limit: int = 50, offset: int = 0
    ) -> list[Doctor] | None:
        """
        Fetch all active doctors with a specific specialization.

        Args:
            specialization: Doctor specialization
            limit: Number of records to fetch
            offset: Offset from start

        Returns:
            List of Doctor models or None if error
        """
        query = """
            SELECT * FROM doctors
            WHERE specialization = %(specialization)s AND is_active = TRUE
            ORDER BY years_experience DESC, created_at DESC
            LIMIT %(limit)s OFFSET %(offset)s;
        """
        params = {"specialization": specialization, "limit": limit, "offset": offset}

        try:
            rows = self._postgres_client.execute_query(query, params, fetch="all")
            if not rows:
                return []
            return [Doctor(**row) for row in rows]
        except Exception as e:
            self._logger.error(f"Error fetching doctors by specialization: {str(e)}")
            return None

    async def search_doctors(
        self, query_text: str, limit: int = 50, offset: int = 0
    ) -> list[Doctor] | None:
        """
        Search doctors by name or specialization (case-insensitive).

        Args:
            query_text: Search term
            limit: Number of records to fetch
            offset: Offset from start

        Returns:
            List of Doctor models or None if error
        """
        query = """
            SELECT * FROM doctors
            WHERE is_active = TRUE AND (
                LOWER(first_name) ILIKE %(query)s OR
                LOWER(last_name) ILIKE %(query)s OR
                LOWER(specialization) ILIKE %(query)s
            )
            ORDER BY first_name, last_name
            LIMIT %(limit)s OFFSET %(offset)s;
        """
        params = {"query": f"%{query_text}%", "limit": limit, "offset": offset}

        try:
            rows = self._postgres_client.execute_query(query, params, fetch="all")
            if not rows:
                return []
            return [Doctor(**row) for row in rows]
        except Exception as e:
            self._logger.error(f"Error searching doctors: {str(e)}")
            return None
