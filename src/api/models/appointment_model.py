# api/models/appointment_model.py
from pydantic import BaseModel, Field
from datetime import datetime, date, time, timezone
from uuid import UUID, uuid4
from enum import Enum


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class AppointmentStatus(str, Enum):
    scheduled = "scheduled"
    confirmed = "confirmed"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"
    rescheduled = "rescheduled"


class AppointmentType(str, Enum):
    consultation = "consultation"
    follow_up = "follow_up"
    emergency = "emergency"
    telemedicine = "telemedicine"


class PaymentStatus(str, Enum):
    pending = "pending"
    paid = "paid"
    refunded = "refunded"
    cancelled = "cancelled"


class Appointment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    appointment_number: str | None = None  # auto-generated like APT-20260406-1430-A7F2
    patient_id: UUID
    doctor_id: UUID
    chat_session_id: UUID | None = None  # reference to originating chat session
    appointment_date: date
    start_time: time
    end_time: time
    appointment_type: AppointmentType = Field(default=AppointmentType.consultation)
    status: AppointmentStatus = Field(default=AppointmentStatus.scheduled)
    consultation_fee: float | None = None
    payment_status: PaymentStatus = Field(default=PaymentStatus.pending)
    cancellation_reason: str | None = None
    rescheduled_from_id: UUID | None = None  # if this is a rescheduled appointment
    patient_notes: str | None = None  # notes from the chat session
    doctor_notes: str | None = None  # notes added by doctor after consultation
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)

    class ConfigDict:
        from_attributes = True
        use_enum_values = True
