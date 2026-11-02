from src.api.agent_runtime import (
    format_messages_for_runner,
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
