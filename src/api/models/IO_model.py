from pydantic import BaseModel, Field
from uuid import uuid4, UUID
from api.models.patient_model import Patient


class InputModel(BaseModel):
    session_id: UUID = Field(default_factory=uuid4)
    patient: Patient
    input: str = Field(max_length=1024)


class OutputModel(BaseModel):
    output: str


class Profile(BaseModel):
    name: str


class Metadata(BaseModel):
    display_phone_number: str
    phone_number_id: str


class Text(BaseModel):
    body: str


class Message(BaseModel):
    from_: str = "from"  # 'from' is a reserved keyword in Python
    id: str
    timestamp: str
    text: Text | None = None
    type: str


class Contact(BaseModel):
    profile: Profile
    wa_id: str


class Value(BaseModel):
    messaging_product: str
    metadata: Metadata
    contacts: list[Contact]
    messages: list[Message]


class Change(BaseModel):
    value: Value
    field: str


class Entry(BaseModel):
    id: str
    changes: list[Change]


class WhatsAppWebhookRequest(BaseModel):
    object: str
    entry: list[Entry]
