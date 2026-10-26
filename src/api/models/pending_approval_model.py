"""A paused agent run waiting for the patient's approval."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel


class PendingApproval(BaseModel):
    chat_session_id: UUID
    run_state: str  # RunState.to_string()
    user_item: dict[str, Any]
    user_message_sequence: int
    # 'processing' while a decision is being applied (see PendingApprovalService)
    status: str = "pending"
