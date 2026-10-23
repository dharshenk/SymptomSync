"""Patient intake state and partial-update schemas."""

from datetime import date, datetime, time, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.api.models.patient_model import Gender


class PatientIntakeUpdate(BaseModel):
    """Only explicitly supplied fields are written during an update."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    age: int | None = Field(default=None, ge=0, le=150)
    gender: Gender | None = None
    symptoms: str | None = None
    pre_existing_conditions: str | None = None
    medications: str | None = None
    preferred_date: date | None = None
    preferred_start_time: time | None = None
    current_step: str | None = Field(default=None, max_length=100)
    status: Literal["in_progress", "completed", "abandoned"] = "in_progress"
    completed_at: datetime | None = None


class PatientIntakeState(PatientIntakeUpdate):
    """The current intake details for one chat session."""

    id: UUID = Field(default_factory=uuid4)
    chat_session_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
