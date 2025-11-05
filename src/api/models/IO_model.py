from pydantic import BaseModel, Field
from uuid import uuid4, UUID
from api.models.patient_model import Patient


class InputModel(BaseModel):
    session_id: UUID = Field(default_factory=uuid4)
    patient: Patient
    input: str = Field(max_length=1024)


class OutputModel(BaseModel):
    output: str
