# api/models/doctor_model.py
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime, timezone
from uuid import UUID, uuid4


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Doctor(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: str
    license_number: str
    specialization: str
    years_experience: int | None = None
    qualification: str | None = None
    hospital_affiliation: str | None = None
    consultation_fee: float | None = None  # Nullable in DB
    consultation_duration: int = Field(default=30, description="Duration in minutes")
    bio: str | None = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_now_utc)
    updated_at: datetime = Field(default_factory=_now_utc)

    class Config:
        from_attributes = True
        use_enum_values = True
