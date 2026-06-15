"""Integration tests for DoctorService."""

import pytest
from uuid import uuid4

from src.api.clients.postgres_sql_client import PostgresSQLClient
from src.api.services.doctor_service import DoctorService
from src.api.models.doctor_model import Doctor


# ============================================
# UNIT TESTS (no DB required)
# ============================================


class TestDoctorModelValidation:
    """Pure unit tests for Doctor model constraints."""

    def test_doctor_defaults(self):
        """Default is_active=True, consultation_duration=30."""
        doctor = Doctor(
            first_name="A",
            last_name="B",
            email="a@b.com",
            phone_number="+1000",
            license_number="LIC-000",
            specialization="Dermatology",
        )
        assert doctor.is_active is True
        assert doctor.consultation_duration == 30
        assert doctor.years_experience is None

    def test_doctor_uuid_auto_generated(self):
        """UUID is auto-generated when not supplied."""
        d1 = Doctor(
            first_name="A",
            last_name="B",
            email="a@b.com",
            phone_number="+1001",
            license_number="L1",
            specialization="X",
        )
        d2 = Doctor(
            first_name="C",
            last_name="D",
            email="c@d.com",
            phone_number="+1002",
            license_number="L2",
            specialization="Y",
        )
        assert d1.id != d2.id


# ============================================
# INTEGRATION TESTS
# ============================================


@pytest.mark.integration
class TestDoctorServiceCreate:
    """Tests for creating doctor records."""

    @pytest.fixture(autouse=True)
    def _cleanup(self, db_client: PostgresSQLClient):
        self._created_ids: list[str] = []
        yield
        for did in self._created_ids:
            db_client.execute_command(
                "DELETE FROM doctors WHERE id = %(id)s;", {"id": did}
            )

    async def test_create_doctor_returns_true(self, doctor_service: DoctorService):
        doctor = Doctor(
            first_name="New",
            last_name="Doc",
            email="new.doc@example.com",
            phone_number="+19990000101",
            license_number="LIC-NEW-001",
            specialization="Cardiology",
            years_experience=5,
            consultation_fee=200.00,
        )
        self._created_ids.append(str(doctor.id))

        result = await doctor_service.create_doctor(doctor)
        assert result is True

    async def test_create_doctor_persists_in_db(self, doctor_service: DoctorService):
        doctor = Doctor(
            first_name="Persist",
            last_name="Doc",
            email="persist.doc@example.com",
            phone_number="+19990000102",
            license_number="LIC-NEW-002",
            specialization="Neurology",
        )
        self._created_ids.append(str(doctor.id))

        await doctor_service.create_doctor(doctor)
        fetched = await doctor_service.get_doctor(doctor.id)

        assert fetched is not None
        assert fetched.first_name == "Persist"
        assert fetched.specialization == "Neurology"

    async def test_create_duplicate_license_raises(self, doctor_service: DoctorService):
        doctor1 = Doctor(
            first_name="Dup",
            last_name="One",
            email="dup1.doc@example.com",
            phone_number="+19990000103",
            license_number="LIC-DUP-001",
            specialization="Ortho",
        )
        doctor2 = Doctor(
            first_name="Dup",
            last_name="Two",
            email="dup2.doc@example.com",
            phone_number="+19990000104",
            license_number="LIC-DUP-001",  # same license
            specialization="Ortho",
        )
        self._created_ids.extend([str(doctor1.id), str(doctor2.id)])

        await doctor_service.create_doctor(doctor1)
        with pytest.raises(Exception):
            await doctor_service.create_doctor(doctor2)


@pytest.mark.integration
class TestDoctorServiceRead:
    """Tests for reading doctor records."""

    async def test_get_doctor_by_id(
        self, doctor_service: DoctorService, sample_doctor: Doctor
    ):
        fetched = await doctor_service.get_doctor(sample_doctor.id)

        assert fetched is not None
        assert fetched.id == sample_doctor.id
        assert fetched.first_name == sample_doctor.first_name

    async def test_get_doctor_not_found(self, doctor_service: DoctorService):
        result = await doctor_service.get_doctor(uuid4())
        assert result is None

    async def test_get_doctor_by_license(
        self, doctor_service: DoctorService, sample_doctor: Doctor
    ):
        fetched = await doctor_service.get_doctor_by_license(
            sample_doctor.license_number
        )

        assert fetched is not None
        assert fetched.id == sample_doctor.id

    async def test_get_doctor_by_license_not_found(self, doctor_service: DoctorService):
        result = await doctor_service.get_doctor_by_license("NONEXISTENT-LIC")
        assert result is None


@pytest.mark.integration
class TestDoctorServiceUpdate:
    """Tests for updating doctor records."""

    async def test_update_doctor_fields(
        self, doctor_service: DoctorService, sample_doctor: Doctor
    ):
        updates = {"bio": "Updated bio text", "years_experience": 15}
        result = await doctor_service.update_doctor(sample_doctor.id, updates)
        assert result is True

        fetched = await doctor_service.get_doctor(sample_doctor.id)
        assert fetched is not None
        assert fetched.bio == "Updated bio text"
        assert fetched.years_experience == 15

    async def test_update_empty_dict_returns_false(
        self, doctor_service: DoctorService, sample_doctor: Doctor
    ):
        result = await doctor_service.update_doctor(sample_doctor.id, {})
        assert result is False

    async def test_update_nonexistent_doctor_returns_false(
        self, doctor_service: DoctorService
    ):
        result = await doctor_service.update_doctor(uuid4(), {"bio": "Ghost"})
        assert result is False


@pytest.mark.integration
class TestDoctorServiceDelete:
    """Tests for deleting doctor records."""

    async def test_delete_doctor(
        self, doctor_service: DoctorService, db_client: PostgresSQLClient
    ):
        doctor = Doctor(
            first_name="Delete",
            last_name="Me",
            email="delete.doc@example.com",
            phone_number="+19990000110",
            license_number="LIC-DEL-001",
            specialization="Pediatrics",
        )
        await doctor_service.create_doctor(doctor)

        result = await doctor_service.delete_doctor(doctor.id)
        assert result is True

        fetched = await doctor_service.get_doctor(doctor.id)
        assert fetched is None

    async def test_delete_nonexistent_doctor_returns_false(
        self, doctor_service: DoctorService
    ):
        result = await doctor_service.delete_doctor(uuid4())
        assert result is False


@pytest.mark.integration
class TestDoctorServiceDeactivate:
    """Tests for soft-deleting (deactivating) doctor records."""

    async def test_deactivate_doctor(
        self, doctor_service: DoctorService, sample_doctor: Doctor
    ):
        result = await doctor_service.deactivate_doctor(sample_doctor.id)
        assert result is True

        fetched = await doctor_service.get_doctor(sample_doctor.id)
        assert fetched is not None
        assert fetched.is_active is False

    async def test_deactivate_nonexistent_returns_false(
        self, doctor_service: DoctorService
    ):
        result = await doctor_service.deactivate_doctor(uuid4())
        assert result is False


@pytest.mark.integration
class TestDoctorServiceList:
    """Tests for listing and searching doctors."""

    @pytest.fixture(autouse=True)
    def _setup_doctors(self, db_client: PostgresSQLClient):
        """Insert a small set of doctors for list/search tests."""
        self._ids: list[str] = []

        doctors = [
            Doctor(
                first_name="Alice",
                last_name="Cardio",
                email="alice.cardio@example.com",
                phone_number="+19990000201",
                license_number="LIC-LIST-001",
                specialization="Cardiology",
                years_experience=20,
            ),
            Doctor(
                first_name="Bob",
                last_name="Cardio",
                email="bob.cardio@example.com",
                phone_number="+19990000202",
                license_number="LIC-LIST-002",
                specialization="Cardiology",
                years_experience=10,
            ),
            Doctor(
                first_name="Charlie",
                last_name="Neuro",
                email="charlie.neuro@example.com",
                phone_number="+19990000203",
                license_number="LIC-LIST-003",
                specialization="Neurology",
                years_experience=15,
            ),
        ]

        for doc in doctors:
            import json

            params = json.loads(doc.model_dump_json())
            params["id"] = str(params["id"])
            db_client.execute_command(
                """
                INSERT INTO doctors (
                    id, first_name, last_name, email, phone_number,
                    license_number, specialization, years_experience,
                    consultation_duration, is_active
                )
                VALUES (
                    %(id)s, %(first_name)s, %(last_name)s, %(email)s, %(phone_number)s,
                    %(license_number)s, %(specialization)s, %(years_experience)s,
                    %(consultation_duration)s, %(is_active)s
                );
                """,
                params,
            )
            self._ids.append(str(doc.id))

        yield

        for did in self._ids:
            db_client.execute_command(
                "DELETE FROM doctors WHERE id = %(id)s;", {"id": did}
            )

    async def test_list_doctors_all_active(self, doctor_service: DoctorService):
        result = await doctor_service.list_doctors()
        assert result is not None
        assert len(result) >= 3

    async def test_list_doctors_by_specialization(self, doctor_service: DoctorService):
        result = await doctor_service.list_doctors(specialization="Cardiology")
        assert result is not None
        assert all(d.specialization == "Cardiology" for d in result)
        assert len(result) >= 2

    async def test_get_doctors_by_specialization(self, doctor_service: DoctorService):
        result = await doctor_service.get_doctors_by_specialization("Neurology")
        assert result is not None
        assert len(result) >= 1
        assert result[0].specialization == "Neurology"

    async def test_search_doctors_by_name(self, doctor_service: DoctorService):
        result = await doctor_service.search_doctors("Alice")
        assert result is not None
        assert any(d.first_name == "Alice" for d in result)

    async def test_search_doctors_by_specialization(
        self, doctor_service: DoctorService
    ):
        result = await doctor_service.search_doctors("cardio")
        assert result is not None
        assert len(result) >= 2

    async def test_list_doctors_with_pagination(self, doctor_service: DoctorService):
        result = await doctor_service.list_doctors(limit=1, offset=0)
        assert result is not None
        assert len(result) == 1

    async def test_list_doctors_empty_result(self, doctor_service: DoctorService):
        result = await doctor_service.list_doctors(specialization="NoSuchSpecialty")
        assert result == []
