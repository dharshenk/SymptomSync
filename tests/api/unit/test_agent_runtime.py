"""AgentRuntime through the real SDK with a scripted model."""

from datetime import date

import pytest
from agents import Agent

from src.api import agent_runtime
from src.api.agent_runtime import AgentRuntime, Finished, NeedsApproval
from src.api.agent_tools.book_appointment import book_appointment
from src.api.models.chat_model import Decision
from tests.api.fake_agent_runtime import FakeAgentRuntime
from tests.api.unit.test_hitl_resume import (
    REPLY,
    TOOL_CALL,
    ScriptedModel,
    context_with_booking_spy,
)


@pytest.fixture(autouse=True)
def prompt_file(monkeypatch, tmp_path):
    path = tmp_path / "prompt.txt"
    path.write_text("Today is {{current_date}}.")
    monkeypatch.setattr(agent_runtime, "SYSTEM_PROMPT_PATH", str(path))
    return path


def runtime_for(*outputs):
    model = ScriptedModel(*outputs)
    agent = Agent(name="a", model=model, tools=[book_appointment])
    return AgentRuntime(agent)


async def test_run_finishes_with_reply_text_and_plain_items():
    context, _ = context_with_booking_spy()

    outcome = await runtime_for(REPLY).run([], "hi", context)

    assert isinstance(outcome, Finished)
    assert outcome.text == "ok"
    assert all(isinstance(item, dict) for item in outcome.items)


async def test_run_pauses_with_a_state_string():
    context, booked = context_with_booking_spy()

    outcome = await runtime_for(TOOL_CALL).run([], "book", context)

    assert isinstance(outcome, NeedsApproval)
    assert isinstance(outcome.state, str) and not booked


async def test_resume_go_ahead_books_with_the_supplied_context():
    context, _ = context_with_booking_spy()
    paused = await runtime_for(TOOL_CALL).run([], "book", context)

    resumed_context, booked = context_with_booking_spy()
    outcome = await runtime_for(REPLY).resume(
        paused.state, resumed_context, Decision.GO_AHEAD
    )

    assert isinstance(outcome, Finished) and outcome.text == "ok"
    assert len(booked) == 1


async def test_resume_changes_needed_does_not_book_and_tells_the_model():
    context, _ = context_with_booking_spy()
    paused = await runtime_for(TOOL_CALL).run([], "book", context)

    resumed_context, booked = context_with_booking_spy()
    outcome = await runtime_for(REPLY).resume(
        paused.state, resumed_context, Decision.CHANGES_NEEDED
    )

    assert booked == []
    assert any(
        item.get("output") == agent_runtime.CHANGES_REJECTION_MESSAGE
        for item in outcome.items
    )


def test_system_prompt_has_the_date_and_no_time_of_day():
    rendered = agent_runtime.get_system_prompt()

    assert rendered == f"Today is {date.today().strftime('%A, %B %d, %Y')}."


def test_v2_prompt_uses_the_rendered_date():
    text = open("src/api/prompts/patient_intake_prompt_v2.txt").read()
    assert "{{current_date}}" in text and "[Current date" not in text


async def test_fake_runtime_returns_scripted_outcomes_and_records_calls():
    fake = FakeAgentRuntime(Finished("a", []), NeedsApproval("s"))
    context = object()

    first = await fake.run([], "hi", context)
    second = await fake.resume("s", context, Decision.GO_AHEAD)

    assert (first.text, second.state) == ("a", "s")
    assert [call[0] for call in fake.calls] == ["run", "resume"]
