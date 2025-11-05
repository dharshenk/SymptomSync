# api/models/patient_model.py
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime, date, timezone
from uuid import UUID, uuid4
from enum import Enum


class Gender(str, Enum):
    male = "male"
    female = "female"
    prefer_not_to_say = "prefer_not_to_say"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Patient(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    patient_id: str = Field(..., description="phone number")
    first_name: str
    last_name: str
    email: EmailStr | None = None
    phone_number: str
    date_of_birth: date | None = None
    gender: Gender | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)

    class Config:
        from_attributes = True
        use_enum_values = True
