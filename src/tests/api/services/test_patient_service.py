"""Integration tests for PatientService."""

import pytest
from uuid import uuid4
from datetime import date

from api.clients.postgres_sql_client import PostgresSQLClient
from api.services.patient_service import PatientService
from api.models.patient_model import Patient


# ============================================
# UNIT TESTS (no DB required)
# ============================================


class TestPatientModelValidation:
    """Pure unit tests for Patient model constraints."""

    def test_patient_defaults(self):
        """Default is_active should be True and optional fields None."""
        patient = Patient(patient_ph_no="+11111111111")
        assert patient.is_active is True
        assert patient.first_name is None
        assert patient.email is None
        assert patient.date_of_birth is None

    def test_patient_uuid_auto_generated(self):
        """UUID is auto-generated when not provided."""
        p1 = Patient(patient_ph_no="+11111111111")
        p2 = Patient(patient_ph_no="+22222222222")
        assert p1.id != p2.id

    def test_patient_with_all_fields(self):
        """Model accepts all optional fields."""
        patient = Patient(
            patient_ph_no="+11111111111",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            date_of_birth=date(1990, 5, 20),
            gender="male",
            emergency_contact_name="Jane Doe",
            emergency_contact_phone="+22222222222",
        )
        assert patient.first_name == "John"
        assert patient.gender == "male"


# ============================================
# INTEGRATION TESTS
# ============================================


@pytest.mark.integration
class TestPatientServiceCreate:
    """Tests for creating patient records."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, db_client: PostgresSQLClient):
        """Remove any rows created during the test."""
        self._created_ids: list[str] = []
        yield
        for pid in self._created_ids:
            db_client.execute_command(
                "DELETE FROM patients WHERE id = %(id)s;", {"id": pid}
            )

    async def test_create_patient_returns_patient(
        self, patient_service: PatientService
    ):
        """Successful insert returns created Patient instance."""
        patient = Patient(
            patient_ph_no="+19990000001",
            first_name="Create",
            last_name="Test",
            email="create.test@example.com",
        )
        self._created_ids.append(str(patient.id))

        result = await patient_service.create_patient(patient)
        assert isinstance(result, Patient)

    async def test_create_patient_persists_in_db(self, patient_service: PatientService):
        """Record is retrievable after creation."""
        patient = Patient(
            patient_ph_no="+19990000002",
            first_name="Persist",
            last_name="Check",
            email="persist.check@example.com",
        )
        self._created_ids.append(str(patient.id))

        await patient_service.create_patient(patient)
        fetched = await patient_service.get_patient(patient.id)

        assert fetched is not None
        assert fetched.first_name == "Persist"
        assert fetched.patient_ph_no == "+19990000002"

    async def test_create_duplicate_phone_raises(self, patient_service: PatientService):
        """Inserting a duplicate patient_ph_no raises (UNIQUE constraint)."""
        patient1 = Patient(
            patient_ph_no="+19990000003",
            first_name="Dup",
            last_name="One",
            email="dup1@example.com",
        )
        patient2 = Patient(
            patient_ph_no="+19990000003",
            first_name="Dup",
            last_name="Two",
            email="dup2@example.com",
        )
        self._created_ids.extend([str(patient1.id), str(patient2.id)])

        await patient_service.create_patient(patient1)
        with pytest.raises(Exception):
            await patient_service.create_patient(patient2)


@pytest.mark.integration
class TestPatientServiceRead:
    """Tests for reading patient records."""

    async def test_get_patient_by_id(
        self, patient_service: PatientService, sample_patient: Patient
    ):
        """Fetch patient by UUID returns correct record."""
        fetched = await patient_service.get_patient(sample_patient.id)

        assert fetched is not None
        assert fetched.id == sample_patient.id
        assert fetched.first_name == sample_patient.first_name
        assert fetched.email == sample_patient.email

    async def test_get_patient_not_found(self, patient_service: PatientService):
        """Non-existent UUID returns None."""
        result = await patient_service.get_patient(uuid4())
        assert result is None

    async def test_get_patient_by_phone_number(
        self, patient_service: PatientService, sample_patient: Patient
    ):
        """Fetch by phone number returns correct record."""
        fetched = await patient_service.get_patient_by_patient_ph_no(
            sample_patient.patient_ph_no
        )

        assert fetched is not None
        assert fetched.id == sample_patient.id

    async def test_get_patient_by_phone_not_found(
        self, patient_service: PatientService
    ):
        """Non-existent phone number returns None."""
        result = await patient_service.get_patient_by_patient_ph_no("+00000000000")
        assert result is None


@pytest.mark.integration
class TestPatientServiceUpdate:
    """Tests for updating patient records."""

    async def test_update_patient_fields(
        self, patient_service: PatientService, sample_patient: Patient
    ):
        """Updating valid fields returns True and persists changes."""
        updates = {"first_name": "Updated", "last_name": "Name"}
        result = await patient_service.update_patient(sample_patient.id, updates)
        assert result is True

        fetched = await patient_service.get_patient(sample_patient.id)
        assert fetched is not None
        assert fetched.first_name == "Updated"
        assert fetched.last_name == "Name"

    async def test_update_empty_dict_returns_false(
        self, patient_service: PatientService, sample_patient: Patient
    ):
        """Empty updates dict returns False without hitting the DB."""
        result = await patient_service.update_patient(sample_patient.id, {})
        assert result is False

    async def test_update_nonexistent_patient_returns_false(
        self, patient_service: PatientService
    ):
        """Updating a non-existent patient returns False."""
        result = await patient_service.update_patient(uuid4(), {"first_name": "Ghost"})
        assert result is False


@pytest.mark.integration
class TestPatientServiceDelete:
    """Tests for deleting patient records."""

    async def test_delete_patient(
        self, patient_service: PatientService, db_client: PostgresSQLClient
    ):
        """Deleting an existing patient returns True and removes the row."""
        patient = Patient(
            patient_ph_no="+19990000010",
            first_name="Delete",
            last_name="Me",
            email="delete.me@example.com",
        )
        await patient_service.create_patient(patient)

        result = await patient_service.delete_patient(patient.id)
        assert result is True

        fetched = await patient_service.get_patient(patient.id)
        assert fetched is None

    async def test_delete_nonexistent_patient_returns_false(
        self, patient_service: PatientService
    ):
        """Deleting a non-existent patient returns False."""
        result = await patient_service.delete_patient(uuid4())
        assert result is False
