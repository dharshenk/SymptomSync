from pydantic import BaseModel, Field
from uuid import uuid4, UUID


class InputModel(BaseModel):
    session_id: UUID = Field(default_factory=uuid4)
    question: str = Field(max_length=1024)


class OutputModel(BaseModel):
    output: str
