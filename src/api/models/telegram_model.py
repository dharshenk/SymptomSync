from pydantic import BaseModel, Field


class FromUser(BaseModel):
    id: int
    is_bot: bool
    first_name: str
    last_name: str | None = None
    language_code: str


class Chat(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    type: str


class Message(BaseModel):
    message_id: int
    # 'from' is a reserved keyword in Python, so we use an alias
    from_user: FromUser = Field(..., alias="from")
    chat: Chat
    date: int
    text: str


class TelegramUpdate(BaseModel):
    update_id: int
    message: Message

    class Config:
        # This allows you to populate the model using the python-friendly names
        # (like from_user) if you ever create it manually.
        populate_by_name = True
