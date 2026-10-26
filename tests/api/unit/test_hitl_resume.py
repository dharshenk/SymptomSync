"""Pause, serialize, restore and resume book_appointment through the real SDK."""

from agents import (
    Agent,
    Model,
    ModelResponse,
    RunContextWrapper,
    RunState,
    Runner,
    Usage,
)
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from src.api.agent_tools.book_appointment import book_appointment
from tests.api.unit.test_agent_tools_context import FULL, make_context


class ScriptedModel(Model):
    def __init__(self, *outputs):
        self.outputs = list(outputs)

    async def get_response(self, *args, **kwargs):
        return ModelResponse(
            output=[self.outputs.pop(0)], usage=Usage(), response_id=None
        )

    def stream_response(self, *args, **kwargs):
        raise NotImplementedError


TOOL_CALL = ResponseFunctionToolCall(
    type="function_call", call_id="c1", name="book_appointment", arguments="{}"
)
REPLY = ResponseOutputMessage(
    id="m",
    type="message",
    role="assistant",
    status="completed",
    content=[ResponseOutputText(type="output_text", text="ok", annotations=[])],
)


def context_with_booking_spy():
    context = make_context(**FULL)
    booked = []

    async def book(appointment):
        booked.append(appointment)
        return True

    context.appointment_service.book_appointment = book
    return context, booked


async def pause_and_restore():
    paused_context, booked = context_with_booking_spy()
    agent = Agent(name="a", model=ScriptedModel(TOOL_CALL), tools=[book_appointment])
    paused = await Runner.run(
        agent, [{"role": "user", "content": "book"}], context=paused_context
    )
    assert len(paused.interruptions) == 1 and not booked

    saved = paused.to_state().to_string(context_serializer=lambda _: {})

    # New process: fresh agent and a context rebuilt from the database
    resumed_context, booked = context_with_booking_spy()
    resumed_agent = Agent(
        name="a", model=ScriptedModel(REPLY), tools=[book_appointment]
    )
    state = await RunState.from_string(
        resumed_agent, saved, context_override=RunContextWrapper(resumed_context)
    )
    return resumed_agent, state, booked


async def test_go_ahead_books_after_resume():
    agent, state, booked = await pause_and_restore()
    state.approve(state.get_interruptions()[0])

    result = await Runner.run(agent, state)

    assert len(booked) == 1
    assert result.final_output == "ok"


async def test_changes_needed_does_not_book_and_tells_the_model():
    agent, state, booked = await pause_and_restore()
    state.reject(state.get_interruptions()[0], rejection_message="CHANGES")

    result = await Runner.run(agent, state)

    assert booked == []
    outputs = [
        item.to_input_item()["output"]
        for item in result.new_items
        if item.type == "tool_call_output_item"
    ]
    assert outputs == ["CHANGES"]
