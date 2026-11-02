from uuid import uuid4

from src.api.models.chat_session_model import ChatMessage, SenderType
from src.api.whatsapp_webhook_api import (
    format_messages_for_runner,
    messages_to_agent_items,
)


def test_format_without_history():
    result = format_messages_for_runner(user_question="hi", system_prompt="sys")
    assert result == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]


def test_format_replays_tool_items_unchanged():
    previous = [
        {"role": "user", "content": "slots?"},
        {"type": "function_call", "call_id": "c1", "name": "t", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c1", "output": "ok"},
        {"role": "assistant", "content": "here"},
    ]
    result = format_messages_for_runner("next", "sys", previous_items=previous)
    assert result[1:-1] == previous
    assert result[-1] == {"role": "user", "content": "next"}


def test_messages_to_agent_items_maps_roles():
    session_id = uuid4()
    messages = [
        ChatMessage(
            session_id=session_id,
            message_sequence=1,
            sender_type=SenderType.patient,
            message_content="hello",
        ),
        ChatMessage(
            session_id=session_id,
            message_sequence=2,
            sender_type=SenderType.bot,
            message_content="hi there",
        ),
    ]
    assert messages_to_agent_items(messages) == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
