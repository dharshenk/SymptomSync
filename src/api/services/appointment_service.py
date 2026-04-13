# api/services/appointment_service.py
from api.clients.postgres_sql_client import PostgresSQLClient
from api.models.appointment_model import Appointment, AppointmentStatus
from uuid import UUID
import logging
import json
import random
import string
from datetime import date, time


class AppointmentService:
    """Business logic for appointments."""

    def __init__(self, postgres_client: PostgresSQLClient):
        self._postgres_client = postgres_client
        self._logger = logging.getLogger(__name__)

    def _generate_appointment_number(
        self, appointment_date: date, start_time: time
    ) -> str:
        """
        Generate a unique appointment number from date, time slot, and random suffix.
        Format: APT-YYYYMMDD-HHmm-XXXX
        Example: APT-20260406-1430-A7F2
        """
        date_str = appointment_date.strftime("%Y%m%d")
        time_str = start_time.strftime("%H%M")
        random_suffix = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=4)
        )
        return f"APT-{date_str}-{time_str}-{random_suffix}"

    async def get_available_slots(
        self, doctor_id: UUID, appointment_date: str
    ) -> list[dict] | None:
        """
        Get available slots for a doctor on a specific date using the PostgreSQL function.

        Args:
            doctor_id: UUID of the doctor
            appointment_date: Date string in format YYYY-MM-DD

        Returns:
            List of available slots with slot_start and slot_end times, or None if error
        """
        query = """
            SELECT *
            FROM get_available_slots(%(doctor_id)s, %(appointment_date)s::date);
        """
        params = {"doctor_id": str(doctor_id), "appointment_date": appointment_date}

        try:
            rows = self._postgres_client.execute_query(query, params, fetch="all")
            return rows if rows else None
        except Exception as e:
            self._logger.error(f"Error fetching available slots: {str(e)}")
            return None

    async def book_appointment(self, appointment: Appointment) -> bool:
        """
        Book a new appointment and generate appointment_number automatically.

        Args:
            appointment: Appointment model with required fields (appointment_date, start_time, end_time)

        Returns:
            True if the appointment was booked successfully, False if no row was affected.

        Raises:
            DatabaseError: Re-raised from the postgres client on query failure.
        """
        # Generate appointment number from the appointment_date and start_time
        appointment.appointment_number = self._generate_appointment_number(
            appointment.appointment_date, appointment.start_time
        )

        insert_query = """
            INSERT INTO appointments (
                id,
                appointment_number,
                patient_id,
                doctor_id,
                chat_session_id,
                appointment_date,
                start_time,
                end_time,
                appointment_type,
                status,
                consultation_fee,
                payment_status,
                patient_notes
            )
            VALUES (
                %(id)s,
                %(appointment_number)s,
                %(patient_id)s,
                %(doctor_id)s,
                %(chat_session_id)s,
                %(appointment_date)s,
                %(start_time)s,
                %(end_time)s,
                %(appointment_type)s,
                %(status)s,
                %(consultation_fee)s,
                %(payment_status)s,
                %(patient_notes)s
            );
        """

        params = json.loads(appointment.model_dump_json())
        params["id"] = str(params["id"])
        params["patient_id"] = str(params["patient_id"])
        params["doctor_id"] = str(params["doctor_id"])
        if params.get("chat_session_id"):
            params["chat_session_id"] = str(params["chat_session_id"])

        try:
            rowcount = self._postgres_client.execute_command(insert_query, params)
            return rowcount > 0
        except Exception as e:
            self._logger.error(f"Error booking appointment: {str(e)}")
            raise

    async def cancel_appointment(
        self, appointment_id: UUID, reason: str | None = None
    ) -> bool:
        """
        Cancel an appointment by setting its status to 'cancelled'.

        Args:
            appointment_id: UUID of the appointment to cancel
            reason: Optional cancellation reason

        Returns:
            True if the appointment was cancelled, False if the ID was not found.

        Raises:
            DatabaseError: Re-raised from the postgres client on query failure.
        """
        update_query = """
            UPDATE appointments
            SET status = %(status)s,
                cancellation_reason = %(reason)s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(appointment_id)s;
        """
        params = {
            "appointment_id": str(appointment_id),
            "status": AppointmentStatus.cancelled.value,
            "reason": reason,
        }

        try:
            rowcount = self._postgres_client.execute_command(update_query, params)
            if rowcount > 0:
                self._logger.info(f"Appointment {appointment_id} cancelled successfully")
                return True
            self._logger.warning(f"Appointment {appointment_id} not found for cancellation")
            return False
        except Exception as e:
            self._logger.error(f"Error cancelling appointment: {str(e)}")
            raise

    async def get_appointment(self, appointment_id: UUID) -> Appointment | None:
        """
        Fetch an appointment by ID.

        Args:
            appointment_id: UUID of the appointment

        Returns:
            Appointment model or None if not found
        """
        query = "SELECT * FROM appointments WHERE id = %(appointment_id)s;"
        rows = self._postgres_client.execute_query(
            query, {"appointment_id": str(appointment_id)}, fetch="one"
        )

        if not rows:
            return None

        return Appointment(**rows[0])

    async def list_appointments_for_patient(
        self, patient_id: UUID, limit: int = 50, offset: int = 0
    ) -> list[Appointment] | None:
        """
        Fetch all appointments for a patient with pagination.

        Args:
            patient_id: UUID of the patient
            limit: Number of records to fetch
            offset: Offset from start

        Returns:
            List of Appointment models or None if error
        """
        query = """
            SELECT * FROM appointments
            WHERE patient_id = %(patient_id)s
            ORDER BY appointment_date DESC
            LIMIT %(limit)s OFFSET %(offset)s;
        """
        params = {
            "patient_id": str(patient_id),
            "limit": limit,
            "offset": offset,
        }

        try:
            rows = self._postgres_client.execute_query(query, params, fetch="all")
            if not rows:
                return []
            return [Appointment(**row) for row in rows]
        except Exception as e:
            self._logger.error(f"Error listing appointments for patient: {str(e)}")
            return None

    async def list_appointments_for_doctor(
        self, doctor_id: UUID, limit: int = 50, offset: int = 0
    ) -> list[Appointment] | None:
        """
        Fetch all appointments for a doctor with pagination.

        Args:
            doctor_id: UUID of the doctor
            limit: Number of records to fetch
            offset: Offset from start

        Returns:
            List of Appointment models or None if error
        """
        query = """
            SELECT * FROM appointments
            WHERE doctor_id = %(doctor_id)s
            ORDER BY appointment_date DESC
            LIMIT %(limit)s OFFSET %(offset)s;
        """
        params = {
            "doctor_id": str(doctor_id),
            "limit": limit,
            "offset": offset,
        }

        try:
            rows = self._postgres_client.execute_query(query, params, fetch="all")
            if not rows:
                return []
            return [Appointment(**row) for row in rows]
        except Exception as e:
            self._logger.error(f"Error listing appointments for doctor: {str(e)}")
            return None

    async def update_appointment_status(
        self, appointment_id: UUID, new_status: AppointmentStatus
    ) -> bool:
        """
        Update the status of an appointment.

        Args:
            appointment_id: UUID of the appointment
            new_status: New AppointmentStatus value

        Returns:
            True if the status was updated, False if the ID was not found.

        Raises:
            DatabaseError: Re-raised from the postgres client on query failure.
        """
        update_query = """
            UPDATE appointments
            SET status = %(status)s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(appointment_id)s;
        """
        params = {
            "appointment_id": str(appointment_id),
            "status": new_status.value,
        }

        try:
            rowcount = self._postgres_client.execute_command(update_query, params)
            if rowcount == 0:
                self._logger.warning(f"Appointment {appointment_id} not found for status update")
                return False
            return True
        except Exception as e:
            self._logger.error(f"Error updating appointment status: {str(e)}")
            raise

    async def reschedule_appointment(
        self,
        appointment_id: UUID,
        new_appointment_date: date,
        new_start_time: time,
        new_end_time: time,
    ) -> bool:
        """
        Reschedule an appointment to a new date/time.

        Args:
            appointment_id: UUID of the appointment
            new_appointment_date: New appointment date
            new_start_time: New start time
            new_end_time: New end time

        Returns:
            True if the appointment was rescheduled, False if the ID was not found.

        Raises:
            DatabaseError: Re-raised from the postgres client on query failure.
        """
        # Generate new appointment number for rescheduled appointment
        new_appointment_number = self._generate_appointment_number(
            new_appointment_date, new_start_time
        )

        update_query = """
            UPDATE appointments
            SET appointment_date = %(appointment_date)s,
                start_time = %(start_time)s,
                end_time = %(end_time)s,
                appointment_number = %(appointment_number)s,
                status = %(status)s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(appointment_id)s;
        """
        params = {
            "appointment_id": str(appointment_id),
            "appointment_date": new_appointment_date,
            "start_time": new_start_time,
            "end_time": new_end_time,
            "appointment_number": new_appointment_number,
            "status": AppointmentStatus.rescheduled.value,
        }

        try:
            rowcount = self._postgres_client.execute_command(update_query, params)
            if rowcount == 0:
                self._logger.warning(f"Appointment {appointment_id} not found for rescheduling")
                return False
            return True
        except Exception as e:
            self._logger.error(f"Error rescheduling appointment: {str(e)}")
            raise

    async def add_doctor_notes(
        self, appointment_id: UUID, notes: str
    ) -> bool:
        """
        Add doctor notes to an appointment after consultation.

        Args:
            appointment_id: UUID of the appointment
            notes: Doctor notes to add

        Returns:
            True if notes were saved, False if the ID was not found.

        Raises:
            DatabaseError: Re-raised from the postgres client on query failure.
        """
        update_query = """
            UPDATE appointments
            SET doctor_notes = %(notes)s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %(appointment_id)s;
        """
        params = {
            "appointment_id": str(appointment_id),
            "notes": notes,
        }

        try:
            rowcount = self._postgres_client.execute_command(update_query, params)
            if rowcount == 0:
                self._logger.warning(f"Appointment {appointment_id} not found for adding notes")
                return False
            return True
        except Exception as e:
            self._logger.error(f"Error adding doctor notes: {str(e)}")
            raise

    async def get_appointments_by_status(
        self, status: AppointmentStatus, limit: int = 50, offset: int = 0
    ) -> list[Appointment] | None:
        """
        Fetch appointments by status.

        Args:
            status: AppointmentStatus to filter by
            limit: Number of records to fetch
            offset: Offset from start

        Returns:
            List of Appointment models or None if error
        """
        query = """
            SELECT * FROM appointments
            WHERE status = %(status)s
            ORDER BY appointment_date DESC
            LIMIT %(limit)s OFFSET %(offset)s;
        """
        params = {
            "status": status.value,
            "limit": limit,
            "offset": offset,
        }

        try:
            rows = self._postgres_client.execute_query(query, params, fetch="all")
            if not rows:
                return []
            return [Appointment(**row) for row in rows]
        except Exception as e:
            self._logger.error(f"Error fetching appointments by status: {str(e)}")
            return None
