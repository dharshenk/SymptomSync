"""Channel-neutral vocabulary: what the chat flow receives and returns."""

from enum import Enum

from pydantic import BaseModel, Field


class Decision(str, Enum):
    """The Patient's answer to an Approval Prompt."""

    GO_AHEAD = "go_ahead"
    CHANGES_NEEDED = "changes_needed"


class IncomingMessage(BaseModel):
    sender_id: str
    text: str


class IncomingDecision(BaseModel):
    sender_id: str
    decision: Decision


class Choice(BaseModel):
    label: str
    decision: Decision


class Reply(BaseModel):
    """What the assistant sends back; an empty `choices` means plain text."""

    text: str
    choices: list[Choice] = Field(default_factory=list)
