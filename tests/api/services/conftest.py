"""Shared fixtures for service integration tests.

These fixtures provide a real PostgresSQLClient connected to the test database
and service instances backed by that client.  They also handle creation and
cleanup of prerequisite rows so individual tests don't need to worry about
foreign-key dependencies.
"""

import pytest
from collections.abc import Generator
from uuid import uuid4
from datetime import date
import os
from dotenv import load_dotenv

from src.api.clients.postgres_sql_client import PostgresSQLClient, DatabaseConfig
from src.api.services.patient_service import PatientService
from src.api.services.doctor_service import DoctorService
from src.api.services.chat_history_service import ChatHistoryService
from src.api.services.appointment_service import AppointmentService
from src.api.models.patient_model import Patient
from src.api.models.doctor_model import Doctor

load_dotenv()

# ============================================
# DATABASE FIXTURES
# ============================================


@pytest.fixture(scope="session")
def db_config() -> DatabaseConfig:
    return DatabaseConfig(
        host=os.getenv("POSTGRES_TEST_HOST"),
        port=os.getenv("POSTGRES_TEST_PORT"),
        username="test_user",
        password="test_password",  # pragma: allowlist secret
        database="test_db",
        timeout=30,
        min_connections=1,
        max_connections=5,
        connect_timeout=10,
        command_timeout=30,
    )


@pytest.fixture(scope="session")
def db_client(db_config: DatabaseConfig) -> Generator[PostgresSQLClient, None, None]:
    client = PostgresSQLClient(db_config)
    yield client

    client.close()


# ============================================
# SCHEMA FIXTURES
# ============================================


@pytest.fixture(scope="session", autouse=True)
def setup_schema(db_client: PostgresSQLClient) -> Generator[None, None, None]:
    """Create all application tables once per test session, drop on teardown.

    Tables are created in FK-dependency order and dropped in reverse order
    so that foreign-key constraints are always satisfied.
    """
    db_client.execute_command('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    db_client.execute_command(
        """
        CREATE TABLE IF NOT EXISTS patients (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            patient_ph_no VARCHAR(20) UNIQUE NOT NULL,
            first_name VARCHAR(100),
            last_name VARCHAR(100),
            email VARCHAR(255) UNIQUE,
            date_of_birth DATE,
            gender VARCHAR(20) CHECK (gender IN ('male', 'female', 'prefer_not_to_say')),
            emergency_contact_name VARCHAR(100),
            emergency_contact_phone VARCHAR(20),
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    db_client.execute_command(
        """
        CREATE TABLE IF NOT EXISTS doctors (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            first_name VARCHAR(100) NOT NULL,
            last_name VARCHAR(100) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            phone_number VARCHAR(20) UNIQUE NOT NULL,
            license_number VARCHAR(50) UNIQUE NOT NULL,
            specialization VARCHAR(100) NOT NULL,
            years_experience INTEGER,
            qualification VARCHAR(200),
            hospital_affiliation VARCHAR(200),
            consultation_fee DECIMAL(10,2),
            consultation_duration INTEGER DEFAULT 30,
            bio TEXT,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    db_client.execute_command(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
            session_status VARCHAR(20) DEFAULT 'active'
                CHECK (session_status IN ('active', 'completed', 'abandoned')),
            started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP WITH TIME ZONE,
            total_messages INTEGER DEFAULT 0,
            session_summary TEXT,
            appointment_requested BOOLEAN DEFAULT false,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    db_client.execute_command(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
            message_sequence INTEGER NOT NULL,
            sender_type VARCHAR(10) NOT NULL
                CHECK (sender_type IN ('patient', 'bot')),
            message_content TEXT NOT NULL,
            message_type VARCHAR(20) DEFAULT 'text'
                CHECK (message_type IN ('text', 'quick_reply', 'image', 'document', 'location')),
            metadata JSONB,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, message_sequence)
        );
        """
    )

    db_client.execute_command(
        """
        CREATE TABLE IF NOT EXISTS appointments (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            appointment_number VARCHAR(30) UNIQUE NOT NULL,
            patient_id UUID REFERENCES patients(id) ON DELETE CASCADE,
            doctor_id UUID REFERENCES doctors(id) ON DELETE CASCADE,
            chat_session_id UUID REFERENCES chat_sessions(id),
            appointment_date DATE NOT NULL,
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            appointment_type VARCHAR(30) DEFAULT 'consultation'
                CHECK (appointment_type IN ('consultation', 'follow_up', 'emergency', 'telemedicine')),
            status VARCHAR(20) DEFAULT 'scheduled'
                CHECK (status IN ('scheduled', 'confirmed', 'in_progress', 'completed', 'cancelled', 'no_show', 'rescheduled')),
            consultation_fee DECIMAL(10,2),
            payment_status VARCHAR(20) DEFAULT 'pending'
                CHECK (payment_status IN ('pending', 'paid', 'refunded', 'cancelled')),
            cancellation_reason TEXT,
            rescheduled_from_id UUID REFERENCES appointments(id),
            patient_notes TEXT,
            doctor_notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # ---- triggers (same as production schema) ----
    db_client.execute_command(
        """
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in ("patients", "doctors", "appointments"):
        db_client.execute_command(
            f"""
            DROP TRIGGER IF EXISTS update_{table}_updated_at ON {table};
            CREATE TRIGGER update_{table}_updated_at
                BEFORE UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
            """
        )

    db_client.execute_command(
        """
        CREATE OR REPLACE FUNCTION update_session_message_count()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                UPDATE chat_sessions
                SET total_messages = total_messages + 1
                WHERE id = NEW.session_id;
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                UPDATE chat_sessions
                SET total_messages = total_messages - 1
                WHERE id = OLD.session_id;
                RETURN OLD;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    db_client.execute_command(
        """
        DROP TRIGGER IF EXISTS update_chat_session_message_count ON chat_messages;
        CREATE TRIGGER update_chat_session_message_count
            AFTER INSERT OR DELETE ON chat_messages
            FOR EACH ROW EXECUTE FUNCTION update_session_message_count();
        """
    )

    yield

    # Teardown: drop tables in reverse FK order
    for table in (
        "appointments",
        "chat_messages",
        "chat_sessions",
        "doctors",
        "patients",
    ):
        db_client.execute_command(f"DROP TABLE IF EXISTS {table} CASCADE;")

    db_client.execute_command(
        "DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;"
    )
    db_client.execute_command(
        "DROP FUNCTION IF EXISTS update_session_message_count() CASCADE;"
    )


# ============================================
# SERVICE FIXTURES
# ============================================


@pytest.fixture()
def patient_service(db_client: PostgresSQLClient) -> PatientService:
    return PatientService(db_client)


@pytest.fixture()
def doctor_service(db_client: PostgresSQLClient) -> DoctorService:
    return DoctorService(db_client)


@pytest.fixture()
def chat_history_service(db_client: PostgresSQLClient) -> ChatHistoryService:
    return ChatHistoryService(db_client)


@pytest.fixture()
def appointment_service(db_client: PostgresSQLClient) -> AppointmentService:
    return AppointmentService(db_client)


# ============================================
# PREREQUISITE ROW FIXTURES
# ============================================


@pytest.fixture()
def sample_patient(db_client: PostgresSQLClient) -> Generator[Patient, None, None]:
    """Insert a patient row and clean up after the test.

    Many services (chat_history, appointment) require a valid patient FK.
    """
    patient = Patient(
        id=uuid4(),
        patient_ph_no="+10000000001",
        first_name="Test",
        last_name="Patient",
        email="test.patient@example.com",
        date_of_birth=date(1990, 1, 15),
        gender="male",
    )

    db_client.execute_command(
        """
        INSERT INTO patients (id, patient_ph_no, first_name, last_name, email, date_of_birth, gender, is_active)
        VALUES (%(id)s, %(patient_ph_no)s, %(first_name)s, %(last_name)s, %(email)s, %(date_of_birth)s, %(gender)s, %(is_active)s);
        """,
        {
            "id": str(patient.id),
            "patient_ph_no": patient.patient_ph_no,
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "email": patient.email,
            "date_of_birth": patient.date_of_birth,
            "gender": patient.gender,
            "is_active": patient.is_active,
        },
    )

    yield patient

    db_client.execute_command(
        "DELETE FROM patients WHERE id = %(id)s;", {"id": str(patient.id)}
    )


@pytest.fixture()
def sample_doctor(db_client: PostgresSQLClient) -> Generator[Doctor, None, None]:
    """Insert a doctor row and clean up after the test."""
    doctor = Doctor(
        id=uuid4(),
        first_name="Test",
        last_name="Doctor",
        email="test.doctor@example.com",
        phone_number="+10000000002",
        license_number="LIC-TEST-001",
        specialization="General Medicine",
        years_experience=10,
        qualification="MBBS",
        hospital_affiliation="Test Hospital",
        consultation_fee=150.00,
        consultation_duration=30,
        bio="Test doctor bio",
    )

    db_client.execute_command(
        """
        INSERT INTO doctors (
            id, first_name, last_name, email, phone_number,
            license_number, specialization, years_experience,
            qualification, hospital_affiliation, consultation_fee,
            consultation_duration, bio, is_active
        )
        VALUES (
            %(id)s, %(first_name)s, %(last_name)s, %(email)s, %(phone_number)s,
            %(license_number)s, %(specialization)s, %(years_experience)s,
            %(qualification)s, %(hospital_affiliation)s, %(consultation_fee)s,
            %(consultation_duration)s, %(bio)s, %(is_active)s
        );
        """,
        {
            "id": str(doctor.id),
            "first_name": doctor.first_name,
            "last_name": doctor.last_name,
            "email": doctor.email,
            "phone_number": doctor.phone_number,
            "license_number": doctor.license_number,
            "specialization": doctor.specialization,
            "years_experience": doctor.years_experience,
            "qualification": doctor.qualification,
            "hospital_affiliation": doctor.hospital_affiliation,
            "consultation_fee": doctor.consultation_fee,
            "consultation_duration": doctor.consultation_duration,
            "bio": doctor.bio,
            "is_active": doctor.is_active,
        },
    )

    yield doctor

    db_client.execute_command(
        "DELETE FROM doctors WHERE id = %(id)s;", {"id": str(doctor.id)}
    )
