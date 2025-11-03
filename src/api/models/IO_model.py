from pydantic import BaseModel, Field
from uuid import uuid4


class InputModel(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    input: str = Field(max_length=1024)


class OutputModel(BaseModel):
    output: str
