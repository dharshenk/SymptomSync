from pydantic import BaseModel, Field, field_validator
from typing import Any
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4


# --------------------------------------------------------
# ENUMS
# --------------------------------------------------------


class SessionStatus(str, Enum):
    active = "active"
    completed = "completed"
    abandoned = "abandoned"


class SenderType(str, Enum):
    patient = "patient"
    bot = "bot"  # Matches your SQL CHECK constraint


class MessageType(str, Enum):
    text = "text"
    quick_reply = "quick_reply"
    image = "image"
    document = "document"
    location = "location"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------
# CHAT SESSION MODEL
# --------------------------------------------------------


class ChatSession(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    patient_id: UUID | None = Field(None, description="FK to patients.id")
    session_status: SessionStatus = Field(default=SessionStatus.active)
    started_at: datetime = Field(default_factory=_now_utc)
    completed_at: datetime | None = None
    total_messages: int = Field(default=0, ge=0)
    session_summary: str | None = None
    appointment_requested: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_now_utc)

    class ConfigDict:
        from_attributes = True
        use_enum_values = True


# --------------------------------------------------------
# CHAT MESSAGE MODEL
# --------------------------------------------------------


class ChatMessage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID = Field(
        ..., description="FK to chat_sessions.id"
    )  # <-- UUID, not str
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

    class ConfigDict:
        from_attributes = True
        use_enum_values = True
