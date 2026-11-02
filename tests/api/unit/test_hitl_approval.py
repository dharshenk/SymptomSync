"""Human-in-the-loop approval for book_appointment and finalizing a paused run."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.api import chat_application
from src.api.agent_runtime import Finished, NeedsApproval
from src.api.agent_tools.book_appointment import book_appointment
from src.api.models.chat_model import Decision
from src.api.models.pending_approval_model import PendingApproval
from tests.api.unit.test_agent_tools_context import FULL, make_context


async def needs_approval(context):
    wrapper = SimpleNamespace(context=context)
    return await book_appointment.needs_approval(wrapper, {}, "call-1")


async def test_approval_needed_when_intake_complete():
    assert await needs_approval(make_context(**FULL)) is True


@pytest.mark.parametrize("field", list(FULL))
async def test_no_approval_while_any_field_missing(field):
    context = make_context(**{**FULL, field: None})
    assert await needs_approval(context) is False


def test_approval_prompt_has_summary_and_both_choices():
    prompt = chat_application.approval_prompt(make_context(**FULL).patient_intake_state)

    assert "Test Patient" in prompt.text and "09:00 AM" in prompt.text
    assert [(c.label, c.decision) for c in prompt.choices] == [
        ("Go Ahead", Decision.GO_AHEAD),
        ("Changes needed", Decision.CHANGES_NEEDED),
    ]


async def test_finalize_run_saves_state_when_paused():
    context = make_context(**FULL)
    pending_service, history_service = Mock(), Mock()
    pending_service.save = AsyncMock()
    history_service.add_message = AsyncMock()
    history_service.add_agent_items = AsyncMock()

    reply = await chat_application.finalize_run(
        NeedsApproval(state="serialized"),
        context,
        {"role": "user", "content": "x"},
        5,
        history_service,
        pending_service,
    )

    saved: PendingApproval = pending_service.save.await_args.args[0]
    assert (saved.run_state, saved.user_message_sequence) == ("serialized", 5)
    assert [c.decision for c in reply.choices] == [
        Decision.GO_AHEAD,
        Decision.CHANGES_NEEDED,
    ]
    history_service.add_message.assert_not_called()
    history_service.add_agent_items.assert_not_called()


async def test_finalize_run_persists_and_clears_pending_when_done():
    context = make_context(**FULL)
    outcome = Finished(text="Booked!", items=[{"type": "message"}])
    pending_service, history_service = Mock(), Mock()
    pending_service.delete = AsyncMock()
    history_service.add_message = AsyncMock()
    history_service.add_agent_items = AsyncMock()

    reply = await chat_application.finalize_run(
        outcome,
        context,
        {"role": "user"},
        5,
        history_service,
        pending_service,
    )

    assert reply.text == "Booked!" and reply.choices == []
    assert history_service.add_message.await_args.args[0].message_sequence == 6
    history_service.add_agent_items.assert_awaited_once_with(
        context.chat_session_id, [{"role": "user"}, {"type": "message"}]
    )
    pending_service.delete.assert_awaited_once_with(context.chat_session_id)
