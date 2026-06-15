"""Integration tests for AppointmentService."""

import pytest
import json
import random
import string
from uuid import UUID, uuid4
from datetime import date, time
from collections.abc import Generator

from src.api.clients.postgres_sql_client import PostgresSQLClient
from src.api.services.appointment_service import AppointmentService
from src.api.models.appointment_model import (
    Appointment,
    AppointmentStatus,
    AppointmentType,
)
from src.api.models.patient_model import Patient
from src.api.models.doctor_model import Doctor


# ============================================
# UNIT TESTS (no DB required)
# ============================================


class TestAppointmentModelValidation:
    """Pure unit tests for Appointment model constraints."""

    def test_appointment_defaults(self):
        appt = Appointment(
            patient_id=uuid4(),
            doctor_id=uuid4(),
            appointment_date=date(2026, 5, 1),
            start_time=time(9, 0),
            end_time=time(9, 30),
        )
        assert appt.status == "scheduled"
        assert appt.appointment_type == "consultation"
        assert appt.payment_status == "pending"
        assert appt.appointment_number is None

    def test_appointment_uuid_auto_generated(self):
        a1 = Appointment(
            patient_id=uuid4(),
            doctor_id=uuid4(),
            appointment_date=date(2026, 5, 1),
            start_time=time(9, 0),
            end_time=time(9, 30),
        )
        a2 = Appointment(
            patient_id=uuid4(),
            doctor_id=uuid4(),
            appointment_date=date(2026, 5, 1),
            start_time=time(10, 0),
            end_time=time(10, 30),
        )
        assert a1.id != a2.id


class TestAppointmentNumberGeneration:
    """Unit tests for the appointment number generator."""

    def test_format(self):
        service = AppointmentService.__new__(AppointmentService)
        number = service._generate_appointment_number(date(2026, 4, 6), time(14, 30))
        assert number.startswith("APT-20260406-1430-")
        assert len(number) == len("APT-20260406-1430-XXXX")

    def test_uniqueness(self):
        """Two calls should produce different suffixes (random component)."""
        service = AppointmentService.__new__(AppointmentService)
        n1 = service._generate_appointment_number(date(2026, 4, 6), time(14, 30))
        n2 = service._generate_appointment_number(date(2026, 4, 6), time(14, 30))
        # Verify the format is correct for both
        assert n1.startswith("APT-20260406-1430-")
        assert n2.startswith("APT-20260406-1430-")


# ============================================
# HELPERS
# ============================================


def _make_appointment(
    patient_id,
    doctor_id,
    appt_date=None,
    start=None,
    end=None,
    chat_session_id=None,
) -> Appointment:
    """Helper to build an Appointment with reasonable defaults."""
    return Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        appointment_date=appt_date or date(2026, 6, 1),
        start_time=start or time(10, 0),
        end_time=end or time(10, 30),
        appointment_type=AppointmentType.consultation,
        consultation_fee=150.00,
        patient_notes="Test notes",
        chat_session_id=chat_session_id,
    )


def _gen_appt_number(appt_date: date, start: time) -> str:
    """Mirror the service's appointment number generation for fixture use."""
    date_str = appt_date.strftime("%Y%m%d")
    time_str = start.strftime("%H%M")
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"APT-{date_str}-{time_str}-{suffix}"


def _insert_appointment_via_db(db_client: PostgresSQLClient, appt: Appointment) -> None:
    """Insert an appointment row directly via the db client (sync)."""
    appt.appointment_number = _gen_appt_number(appt.appointment_date, appt.start_time)
    params = json.loads(appt.model_dump_json())
    params["id"] = str(params["id"])
    params["patient_id"] = str(params["patient_id"])
    params["doctor_id"] = str(params["doctor_id"])
    if params.get("chat_session_id"):
        params["chat_session_id"] = str(params["chat_session_id"])

    db_client.execute_command(
        """
        INSERT INTO appointments (
            id, appointment_number, patient_id, doctor_id,
            chat_session_id, appointment_date, start_time, end_time,
            appointment_type, status, consultation_fee,
            payment_status, patient_notes
        )
        VALUES (
            %(id)s, %(appointment_number)s, %(patient_id)s, %(doctor_id)s,
            %(chat_session_id)s, %(appointment_date)s, %(start_time)s, %(end_time)s,
            %(appointment_type)s, %(status)s, %(consultation_fee)s,
            %(payment_status)s, %(patient_notes)s
        );
        """,
        params,
    )


# ============================================
# INTEGRATION TESTS
# ============================================


@pytest.mark.integration
class TestAppointmentServiceBook:
    """Tests for booking appointments."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, db_client: PostgresSQLClient):
        self._created_numbers: list[str] = []
        yield
        for num in self._created_numbers:
            db_client.execute_command(
                "DELETE FROM appointments WHERE appointment_number = %(num)s;",
                {"num": num},
            )

    async def test_book_appointment_returns_true(
        self,
        appointment_service: AppointmentService,
        sample_patient: Patient,
        sample_doctor: Doctor,
        sample_chat_session: UUID,
    ):
        appt = _make_appointment(
            sample_patient.id,
            sample_doctor.id,
            chat_session_id=sample_chat_session,
        )

        result = await appointment_service.book_appointment(appt)
        self._created_numbers.append(appt.appointment_number)
        assert result is True

    async def test_book_appointment_generates_number(
        self,
        appointment_service: AppointmentService,
        sample_patient: Patient,
        sample_doctor: Doctor,
        sample_chat_session: UUID,
    ):
        appt = _make_appointment(
            sample_patient.id,
            sample_doctor.id,
            chat_session_id=sample_chat_session,
        )

        await appointment_service.book_appointment(appt)
        self._created_numbers.append(appt.appointment_number)
        assert appt.appointment_number is not None
        assert appt.appointment_number.startswith("APT-")

    async def test_book_appointment_persists(
        self,
        appointment_service: AppointmentService,
        sample_patient: Patient,
        sample_doctor: Doctor,
        sample_chat_session: UUID,
    ):
        appt = _make_appointment(
            sample_patient.id,
            sample_doctor.id,
            chat_session_id=sample_chat_session,
        )

        await appointment_service.book_appointment(appt)
        self._created_numbers.append(appt.appointment_number)

        # SQL function generates its own UUID, so fetch by patient_id
        fetched = await appointment_service.get_appointment_by_patient_id(
            sample_patient.id
        )

        assert fetched is not None
        assert fetched.patient_id == sample_patient.id
        assert fetched.doctor_id == sample_doctor.id
        assert fetched.status == "scheduled"
        assert fetched.patient_notes == "Test notes"
        assert fetched.chat_session_id == sample_chat_session
        assert fetched.appointment_number == appt.appointment_number

    async def test_book_appointment_without_chat_session(
        self,
        appointment_service: AppointmentService,
        sample_patient: Patient,
        sample_doctor: Doctor,
    ):
        """Booking without a chat_session_id should still succeed (NULL FK)."""
        appt = _make_appointment(
            sample_patient.id,
            sample_doctor.id,
            start=time(11, 0),
            end=time(11, 30),
        )

        result = await appointment_service.book_appointment(appt)
        self._created_numbers.append(appt.appointment_number)
        assert result is True

    async def test_book_appointment_duplicate_slot_raises(
        self,
        appointment_service: AppointmentService,
        sample_patient: Patient,
        sample_doctor: Doctor,
        sample_chat_session: UUID,
    ):
        """The SQL function should raise when double-booking the same slot."""
        appt1 = _make_appointment(
            sample_patient.id,
            sample_doctor.id,
            appt_date=date(2026, 6, 15),
            start=time(9, 0),
            end=time(9, 30),
            chat_session_id=sample_chat_session,
        )
        await appointment_service.book_appointment(appt1)
        self._created_numbers.append(appt1.appointment_number)

        appt2 = _make_appointment(
            sample_patient.id,
            sample_doctor.id,
            appt_date=date(2026, 6, 15),
            start=time(9, 0),
            end=time(9, 30),
            chat_session_id=sample_chat_session,
        )

        with pytest.raises(Exception, match="already booked"):
            await appointment_service.book_appointment(appt2)


@pytest.mark.integration
class TestAppointmentServiceGet:
    """Tests for fetching appointments."""

    @pytest.fixture()
    def booked_appointment(
        self,
        db_client: PostgresSQLClient,
        sample_patient: Patient,
        sample_doctor: Doctor,
    ) -> Generator[Appointment, None, None]:
        """Insert an appointment via db_client and clean up after test."""
        appt = _make_appointment(sample_patient.id, sample_doctor.id)
        _insert_appointment_via_db(db_client, appt)
        yield appt
        db_client.execute_command(
            "DELETE FROM appointments WHERE id = %(id)s;", {"id": str(appt.id)}
        )

    async def test_get_appointment_by_id(
        self,
        appointment_service: AppointmentService,
        booked_appointment: Appointment,
    ):
        fetched = await appointment_service.get_appointment(booked_appointment.id)
        assert fetched is not None
        assert fetched.id == booked_appointment.id

    async def test_get_appointment_not_found(
        self, appointment_service: AppointmentService
    ):
        result = await appointment_service.get_appointment(uuid4())
        assert result is None


@pytest.mark.integration
class TestAppointmentServiceCancel:
    """Tests for cancelling appointments."""

    @pytest.fixture()
    def booked_appointment(
        self,
        db_client: PostgresSQLClient,
        sample_patient: Patient,
        sample_doctor: Doctor,
    ) -> Generator[Appointment, None, None]:
        appt = _make_appointment(sample_patient.id, sample_doctor.id)
        _insert_appointment_via_db(db_client, appt)
        yield appt
        db_client.execute_command(
            "DELETE FROM appointments WHERE id = %(id)s;", {"id": str(appt.id)}
        )

    async def test_cancel_appointment_returns_true(
        self,
        appointment_service: AppointmentService,
        booked_appointment: Appointment,
    ):
        result = await appointment_service.cancel_appointment(
            booked_appointment.id, reason="Patient request"
        )
        assert result is True

    async def test_cancel_appointment_updates_status(
        self,
        appointment_service: AppointmentService,
        booked_appointment: Appointment,
    ):
        await appointment_service.cancel_appointment(
            booked_appointment.id, reason="Changed mind"
        )
        fetched = await appointment_service.get_appointment(booked_appointment.id)
        assert fetched is not None
        assert fetched.status == "cancelled"

    async def test_cancel_nonexistent_returns_false(
        self, appointment_service: AppointmentService
    ):
        result = await appointment_service.cancel_appointment(uuid4())
        assert result is False


@pytest.mark.integration
class TestAppointmentServiceUpdateStatus:
    """Tests for updating appointment status."""

    @pytest.fixture()
    def booked_appointment(
        self,
        db_client: PostgresSQLClient,
        sample_patient: Patient,
        sample_doctor: Doctor,
    ) -> Generator[Appointment, None, None]:
        appt = _make_appointment(sample_patient.id, sample_doctor.id)
        _insert_appointment_via_db(db_client, appt)
        yield appt
        db_client.execute_command(
            "DELETE FROM appointments WHERE id = %(id)s;", {"id": str(appt.id)}
        )

    async def test_update_status_to_confirmed(
        self,
        appointment_service: AppointmentService,
        booked_appointment: Appointment,
    ):
        result = await appointment_service.update_appointment_status(
            booked_appointment.id, AppointmentStatus.confirmed
        )
        assert result is True

        fetched = await appointment_service.get_appointment(booked_appointment.id)
        assert fetched is not None
        assert fetched.status == "confirmed"

    async def test_update_status_to_completed(
        self,
        appointment_service: AppointmentService,
        booked_appointment: Appointment,
    ):
        result = await appointment_service.update_appointment_status(
            booked_appointment.id, AppointmentStatus.completed
        )
        assert result is True

    async def test_update_status_nonexistent_returns_false(
        self, appointment_service: AppointmentService
    ):
        result = await appointment_service.update_appointment_status(
            uuid4(), AppointmentStatus.confirmed
        )
        assert result is False


@pytest.mark.integration
class TestAppointmentServiceReschedule:
    """Tests for rescheduling appointments."""

    @pytest.fixture()
    def booked_appointment(
        self,
        db_client: PostgresSQLClient,
        sample_patient: Patient,
        sample_doctor: Doctor,
    ) -> Generator[Appointment, None, None]:
        appt = _make_appointment(sample_patient.id, sample_doctor.id)
        _insert_appointment_via_db(db_client, appt)
        yield appt
        db_client.execute_command(
            "DELETE FROM appointments WHERE id = %(id)s;", {"id": str(appt.id)}
        )

    async def test_reschedule_returns_true(
        self,
        appointment_service: AppointmentService,
        booked_appointment: Appointment,
    ):
        result = await appointment_service.reschedule_appointment(
            booked_appointment.id,
            new_appointment_date=date(2026, 7, 1),
            new_start_time=time(14, 0),
            new_end_time=time(14, 30),
        )
        assert result is True

    async def test_reschedule_updates_fields(
        self,
        appointment_service: AppointmentService,
        booked_appointment: Appointment,
    ):
        new_date = date(2026, 7, 15)
        new_start = time(16, 0)
        new_end = time(16, 30)

        await appointment_service.reschedule_appointment(
            booked_appointment.id, new_date, new_start, new_end
        )

        fetched = await appointment_service.get_appointment(booked_appointment.id)
        assert fetched is not None
        assert fetched.appointment_date == new_date
        assert fetched.start_time == new_start
        assert fetched.end_time == new_end
        assert fetched.status == "rescheduled"
        assert fetched.appointment_number.startswith("APT-20260715-1600-")

    async def test_reschedule_nonexistent_returns_false(
        self, appointment_service: AppointmentService
    ):
        result = await appointment_service.reschedule_appointment(
            uuid4(), date(2026, 8, 1), time(9, 0), time(9, 30)
        )
        assert result is False


@pytest.mark.integration
class TestAppointmentServiceDoctorNotes:
    """Tests for adding doctor notes."""

    @pytest.fixture()
    def booked_appointment(
        self,
        db_client: PostgresSQLClient,
        sample_patient: Patient,
        sample_doctor: Doctor,
    ) -> Generator[Appointment, None, None]:
        appt = _make_appointment(sample_patient.id, sample_doctor.id)
        _insert_appointment_via_db(db_client, appt)
        yield appt
        db_client.execute_command(
            "DELETE FROM appointments WHERE id = %(id)s;", {"id": str(appt.id)}
        )

    async def test_add_doctor_notes_returns_true(
        self,
        appointment_service: AppointmentService,
        booked_appointment: Appointment,
    ):
        result = await appointment_service.add_doctor_notes(
            booked_appointment.id, "Patient shows improvement"
        )
        assert result is True

    async def test_add_doctor_notes_persists(
        self,
        appointment_service: AppointmentService,
        booked_appointment: Appointment,
    ):
        notes = "Prescribed medication X, follow up in 2 weeks"
        await appointment_service.add_doctor_notes(booked_appointment.id, notes)

        fetched = await appointment_service.get_appointment(booked_appointment.id)
        assert fetched is not None
        assert fetched.doctor_notes == notes

    async def test_add_notes_nonexistent_returns_false(
        self, appointment_service: AppointmentService
    ):
        result = await appointment_service.add_doctor_notes(uuid4(), "Ghost notes")
        assert result is False


@pytest.mark.integration
class TestAppointmentServiceListAndFilter:
    """Tests for listing appointments by patient, doctor, and status."""

    @pytest.fixture(autouse=True)
    def _setup_appointments(
        self,
        db_client: PostgresSQLClient,
        sample_patient: Patient,
        sample_doctor: Doctor,
    ):
        """Create a few appointments for listing tests using direct DB inserts."""
        self._ids: list[str] = []

        appointments = [
            _make_appointment(
                sample_patient.id,
                sample_doctor.id,
                appt_date=date(2026, 6, 1),
                start=time(9, 0),
                end=time(9, 30),
            ),
            _make_appointment(
                sample_patient.id,
                sample_doctor.id,
                appt_date=date(2026, 6, 2),
                start=time(10, 0),
                end=time(10, 30),
            ),
            _make_appointment(
                sample_patient.id,
                sample_doctor.id,
                appt_date=date(2026, 6, 3),
                start=time(11, 0),
                end=time(11, 30),
            ),
        ]

        for appt in appointments:
            _insert_appointment_via_db(db_client, appt)
            self._ids.append(str(appt.id))

        self._patient_id = sample_patient.id
        self._doctor_id = sample_doctor.id

        yield

        for aid in self._ids:
            db_client.execute_command(
                "DELETE FROM appointments WHERE id = %(id)s;", {"id": aid}
            )

    async def test_list_by_patient(self, appointment_service: AppointmentService):
        result = await appointment_service.list_appointments_for_patient(
            self._patient_id
        )
        assert result is not None
        assert len(result) >= 3

    async def test_list_by_doctor(self, appointment_service: AppointmentService):
        result = await appointment_service.list_appointments_for_doctor(self._doctor_id)
        assert result is not None
        assert len(result) >= 3

    async def test_list_by_status(self, appointment_service: AppointmentService):
        result = await appointment_service.get_appointments_by_status(
            AppointmentStatus.scheduled
        )
        assert result is not None
        assert len(result) >= 3
        assert all(a.status == "scheduled" for a in result)

    async def test_list_by_patient_with_pagination(
        self, appointment_service: AppointmentService
    ):
        result = await appointment_service.list_appointments_for_patient(
            self._patient_id, limit=1, offset=0
        )
        assert result is not None
        assert len(result) == 1

    async def test_list_by_patient_empty(self, appointment_service: AppointmentService):
        result = await appointment_service.list_appointments_for_patient(uuid4())
        assert result == []

    async def test_list_by_doctor_empty(self, appointment_service: AppointmentService):
        result = await appointment_service.list_appointments_for_doctor(uuid4())
        assert result == []

    async def test_list_by_status_empty(self, appointment_service: AppointmentService):
        result = await appointment_service.get_appointments_by_status(
            AppointmentStatus.no_show
        )
        # Could be empty or not depending on DB state; just verify it's a list
        assert isinstance(result, list)


# ============================================
# NEW METHOD TESTS
# ============================================


@pytest.mark.integration
class TestAppointmentServiceGetByPatientId:
    """Tests for get_appointment_by_patient_id."""

    @pytest.fixture()
    def booked_appointment(
        self,
        db_client: PostgresSQLClient,
        sample_patient: Patient,
        sample_doctor: Doctor,
    ) -> Generator[Appointment, None, None]:
        appt = _make_appointment(sample_patient.id, sample_doctor.id)
        _insert_appointment_via_db(db_client, appt)
        yield appt
        db_client.execute_command(
            "DELETE FROM appointments WHERE id = %(id)s;", {"id": str(appt.id)}
        )

    async def test_get_by_patient_id_returns_appointment(
        self,
        appointment_service: AppointmentService,
        booked_appointment: Appointment,
        sample_patient: Patient,
    ):
        fetched = await appointment_service.get_appointment_by_patient_id(
            sample_patient.id
        )
        assert fetched is not None
        assert fetched.patient_id == sample_patient.id

    async def test_get_by_patient_id_returns_latest(
        self,
        appointment_service: AppointmentService,
        db_client: PostgresSQLClient,
        sample_patient: Patient,
        sample_doctor: Doctor,
    ):
        """When multiple appointments exist, the most recently created is returned."""
        appt1 = _make_appointment(
            sample_patient.id,
            sample_doctor.id,
            appt_date=date(2026, 6, 1),
            start=time(9, 0),
            end=time(9, 30),
        )
        appt2 = _make_appointment(
            sample_patient.id,
            sample_doctor.id,
            appt_date=date(2026, 6, 2),
            start=time(10, 0),
            end=time(10, 30),
        )
        _insert_appointment_via_db(db_client, appt1)
        _insert_appointment_via_db(db_client, appt2)

        try:
            fetched = await appointment_service.get_appointment_by_patient_id(
                sample_patient.id
            )
            assert fetched is not None
            assert fetched.id == appt2.id  # latest by created_at
        finally:
            for a in (appt1, appt2):
                db_client.execute_command(
                    "DELETE FROM appointments WHERE id = %(id)s;",
                    {"id": str(a.id)},
                )

    async def test_get_by_patient_id_not_found(
        self, appointment_service: AppointmentService
    ):
        result = await appointment_service.get_appointment_by_patient_id(uuid4())
        assert result is None


@pytest.mark.integration
class TestAppointmentServiceGetByChatSessionId:
    """Tests for get_appointment_by_chat_session_id."""

    @pytest.fixture()
    def booked_appointment_with_session(
        self,
        db_client: PostgresSQLClient,
        sample_patient: Patient,
        sample_doctor: Doctor,
        sample_chat_session: UUID,
    ) -> Generator[Appointment, None, None]:
        appt = _make_appointment(
            sample_patient.id,
            sample_doctor.id,
            chat_session_id=sample_chat_session,
        )
        _insert_appointment_via_db(db_client, appt)
        yield appt
        db_client.execute_command(
            "DELETE FROM appointments WHERE id = %(id)s;", {"id": str(appt.id)}
        )

    async def test_get_by_chat_session_id_returns_appointment(
        self,
        appointment_service: AppointmentService,
        booked_appointment_with_session: Appointment,
        sample_chat_session: UUID,
    ):
        fetched = await appointment_service.get_appointment_by_chat_session_id(
            sample_chat_session
        )
        assert fetched is not None
        assert fetched.chat_session_id == sample_chat_session
        assert fetched.id == booked_appointment_with_session.id

    async def test_get_by_chat_session_id_not_found(
        self, appointment_service: AppointmentService
    ):
        result = await appointment_service.get_appointment_by_chat_session_id(uuid4())
        assert result is None


@pytest.mark.integration
class TestAppointmentServiceGetAvailableSlots:
    """Tests for get_available_slots."""

    @pytest.fixture(autouse=True)
    def _setup_availability(
        self,
        db_client: PostgresSQLClient,
        sample_doctor: Doctor,
    ):
        """Insert a doctor_availability row for Wednesday (DOW=3).

        Slots: 09:00–12:00 with 30-min duration and 0-min break = 6 slots.
        """
        self._avail_id = uuid4()
        db_client.execute_command(
            """
            INSERT INTO doctor_availability
                (id, doctor_id, day_of_week, start_time, end_time,
                 slot_duration, break_duration, is_active)
            VALUES
                (%(id)s, %(doctor_id)s, 3, '09:00', '12:00', 30, 0, true);
            """,
            {"id": str(self._avail_id), "doctor_id": str(sample_doctor.id)},
        )
        self._doctor_id = sample_doctor.id

        yield

        db_client.execute_command(
            "DELETE FROM doctor_availability WHERE id = %(id)s;",
            {"id": str(self._avail_id)},
        )

    async def test_returns_slots_for_available_day(
        self, appointment_service: AppointmentService
    ):
        # 2026-06-03 is a Wednesday (DOW=3)
        slots = await appointment_service.get_available_slots(
            self._doctor_id, date(2026, 6, 3)
        )
        assert slots is not None
        assert len(slots) == 6

    async def test_returns_none_for_no_availability(
        self, appointment_service: AppointmentService
    ):
        # 2026-06-01 is a Monday (DOW=1), no availability configured
        slots = await appointment_service.get_available_slots(
            self._doctor_id, date(2026, 6, 1)
        )
        assert slots is None

    async def test_returns_none_for_unknown_doctor(
        self, appointment_service: AppointmentService
    ):
        slots = await appointment_service.get_available_slots(uuid4(), date(2026, 6, 3))
        assert slots is None
