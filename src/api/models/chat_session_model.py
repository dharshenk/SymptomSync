from pydantic import BaseModel, Field, field_validator
from typing import Any
from datetime import datetime, timezone
from enum import Enum


class SessionStatus(str, Enum):
    active = "active"
    completed = "completed"
    abandoned = "abandoned"


class SenderType(str, Enum):
    patient = "patient"
    copilot = "copilot"


class MessageType(str, Enum):
    text = "text"
    quick_reply = "quick_reply"
    image = "image"
    document = "document"
    location = "location"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ChatSession(BaseModel):
    session_id: str = Field(..., max_length=50)
    patient_id: str | None = Field(..., max_length=50)
    session_status: SessionStatus = Field(default=SessionStatus.active)
    started_at: datetime | None = Field(default_factory=_now_utc)
    completed_at: datetime | None = None
    total_messages: int = Field(default=0, ge=0)
    session_summary: str | None = None
    appointment_requested: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_now_utc)

    @field_validator("session_id")
    @classmethod
    def session_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("session_id must be a non-empty string")
        return v

    class Config:
        orm_mode = True
        use_enum_values = True


class ChatMessage(BaseModel):
    session_id: str = Field(..., max_length=50)
    message_sequence: int = Field(..., ge=0)
    sender_type: SenderType
    message_content: str
    message_type: MessageType = Field(default=MessageType.text)
    metadata: dict[str, Any] | None = None
    timestamp: datetime = Field(default_factory=_now_utc)

    @field_validator("message_content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("message_content must be a non-empty string")
        return v

    class Config:
        orm_mode = True
        use_enum_values = True
