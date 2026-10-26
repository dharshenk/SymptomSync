"""Human-in-the-loop approval for book_appointment and the /webhook dispatcher."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.api import whatsapp_webhook_api as webhook
from src.api.agent_tools.book_appointment import book_appointment
from src.api.clients.telegram_client import TelegramAPIError
from src.api.models.pending_approval_model import PendingApproval
from src.api.models.telegram_model import TelegramWebhookUpdate
from tests.api.unit.test_agent_tools_context import FULL, make_context

USER = {"id": 42, "is_bot": False, "first_name": "Pat", "language_code": "en"}


def callback_query(data):
    return TelegramWebhookUpdate.model_validate(
        {"update_id": 1, "callback_query": {"id": "cb", "from": USER, "data": data}}
    ).callback_query


async def needs_approval(context):
    wrapper = SimpleNamespace(context=context)
    return await book_appointment.needs_approval(wrapper, {}, "call-1")


async def test_approval_needed_when_intake_complete():
    assert await needs_approval(make_context(**FULL)) is True


@pytest.mark.parametrize("field", list(FULL))
async def test_no_approval_while_any_field_missing(field):
    context = make_context(**{**FULL, field: None})
    assert await needs_approval(context) is False


def test_webhook_update_parses_button_press_and_message():
    assert callback_query("approve").data == "approve"
    text = TelegramWebhookUpdate.model_validate({"update_id": 2, "message": MESSAGE})
    assert text.callback_query is None and text.message.text == "hi"


def test_approval_prompt_has_summary_and_both_buttons():
    prompt = webhook.approval_prompt(make_context(**FULL).patient_intake_state)

    assert "Test Patient" in prompt["text"] and "09:00 AM" in prompt["text"]
    buttons = [b for row in prompt["reply_markup"]["inline_keyboard"] for b in row]
    assert [b["callback_data"] for b in buttons] == ["approve", "changes_needed"]


async def test_finalize_run_saves_state_when_paused():
    context = make_context(**FULL)
    state = Mock()
    state.to_string.return_value = "serialized"
    result = SimpleNamespace(interruptions=[object()], to_state=lambda: state)
    pending_service, history_service, telegram = Mock(), Mock(), Mock()
    pending_service.save = AsyncMock()
    history_service.add_message = AsyncMock()
    history_service.add_agent_items = AsyncMock()

    reply = await webhook.finalize_run(
        result,
        context,
        {"role": "user", "content": "x"},
        5,
        history_service,
        pending_service,
        telegram,
        "42",
    )

    saved: PendingApproval = pending_service.save.await_args.args[0]
    assert (saved.run_state, saved.user_message_sequence) == ("serialized", 5)
    assert "reply_markup" in reply
    telegram.send_message.assert_called_once_with("42", **reply)
    history_service.add_message.assert_not_called()
    history_service.add_agent_items.assert_not_called()


async def test_finalize_run_persists_and_clears_pending_when_done():
    context = make_context(**FULL)
    item = Mock()
    item.to_input_item.return_value = {"type": "message"}
    result = SimpleNamespace(interruptions=[], final_output="Booked!", new_items=[item])
    pending_service, history_service, telegram = Mock(), Mock(), Mock()
    pending_service.delete = AsyncMock()
    history_service.add_message = AsyncMock()
    history_service.add_agent_items = AsyncMock()

    reply = await webhook.finalize_run(
        result,
        context,
        {"role": "user"},
        5,
        history_service,
        pending_service,
        telegram,
        "42",
    )

    assert reply == "Booked!"
    telegram.send_message.assert_called_once_with("42", text="Booked!")
    assert history_service.add_message.await_args.args[0].message_sequence == 6
    history_service.add_agent_items.assert_awaited_once_with(
        context.chat_session_id, [{"role": "user"}, {"type": "message"}]
    )
    pending_service.delete.assert_awaited_once_with(context.chat_session_id)


@pytest.fixture
def approval_env(monkeypatch):
    """Everything handle_approval needs, with the agent run stubbed out."""
    interruption = object()
    state = Mock()
    state.get_interruptions.return_value = [interruption]
    monkeypatch.setattr(webhook.RunState, "from_string", AsyncMock(return_value=state))
    monkeypatch.setattr(webhook, "run_agent", AsyncMock(return_value="result"))
    monkeypatch.setattr(
        webhook, "build_tool_context", AsyncMock(return_value=make_context(**FULL))
    )
    monkeypatch.setattr(webhook, "finalize_run", AsyncMock(return_value="final"))
    pending_service = Mock()
    pending_service.save = AsyncMock()
    pending_service.get = AsyncMock(return_value="pending")
    pending_service.claim = AsyncMock(
        return_value=PendingApproval(
            chat_session_id=uuid4(),
            run_state="s",
            user_item={"role": "user"},
            user_message_sequence=2,
        )
    )
    patient_service = Mock()
    patient_service.get_patient_by_patient_ph_no = AsyncMock(
        return_value=SimpleNamespace(id=uuid4())
    )
    intake_service = Mock()
    intake_service.get_intake_state = AsyncMock(
        return_value=make_context(**FULL).patient_intake_state
    )

    telegram = Mock()

    async def call(update):
        return await webhook.handle_approval(
            update,
            patient_service,
            Mock(),
            intake_service,
            pending_service,
            Mock(),
            telegram,
            Mock(),
        )

    return SimpleNamespace(
        call=call,
        state=state,
        interruption=interruption,
        pending_service=pending_service,
        telegram=telegram,
    )


async def test_go_ahead_approves_and_resumes(approval_env):
    reply = await approval_env.call(callback_query("approve"))

    approval_env.state.approve.assert_called_once_with(approval_env.interruption)
    approval_env.state.reject.assert_not_called()
    webhook.run_agent.assert_awaited_once()
    assert reply == "final"


async def test_changes_needed_rejects_with_message_and_resumes(approval_env):
    await approval_env.call(callback_query("changes_needed"))

    approval_env.state.reject.assert_called_once_with(
        approval_env.interruption,
        rejection_message=webhook.CHANGES_REJECTION_MESSAGE,
    )
    approval_env.state.approve.assert_not_called()
    webhook.run_agent.assert_awaited_once()


async def test_nothing_pending_does_not_run_agent(approval_env):
    approval_env.pending_service.claim.return_value = None

    reply = await approval_env.call(callback_query("approve"))

    assert "nothing waiting" in reply
    webhook.run_agent.assert_not_called()


async def test_unknown_decision_reprompts_without_running(approval_env):
    reply = await approval_env.call(callback_query("bogus"))

    assert "reply_markup" in reply
    approval_env.telegram.send_message.assert_called_once_with("42", **reply)
    webhook.run_agent.assert_not_called()


MESSAGE = {
    "message_id": 1,
    "from": USER,
    "chat": {"id": 42, "first_name": "Pat", "type": "private"},
    "date": 0,
    "text": "hi",
}


async def dispatch(monkeypatch, payload):
    handle_approval = AsyncMock(return_value="approval")
    handle_message = AsyncMock(return_value="message")
    monkeypatch.setattr(webhook, "handle_approval", handle_approval)
    monkeypatch.setattr(webhook, "handle_message", handle_message)
    reply = await webhook.telegram_webhook(
        TelegramWebhookUpdate.model_validate({"update_id": 1, **payload}),
        *[Mock() for _ in range(7)],
    )
    return reply, handle_approval, handle_message


async def test_webhook_routes_button_press_to_approval(monkeypatch):
    payload = {"callback_query": {"id": "cb", "from": USER, "data": "approve"}}

    reply, handle_approval, handle_message = await dispatch(monkeypatch, payload)

    assert reply == "approval"
    handle_approval.assert_awaited_once()
    handle_message.assert_not_called()


async def test_webhook_routes_text_message_to_agent(monkeypatch):
    reply, handle_approval, handle_message = await dispatch(
        monkeypatch, {"message": MESSAGE}
    )

    assert reply == "message"
    handle_message.assert_awaited_once()
    handle_approval.assert_not_called()


async def test_webhook_rejects_update_with_neither(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await dispatch(monkeypatch, {})
    assert exc.value.status_code == 422


def test_deliver_reply_swallows_telegram_errors():
    telegram = Mock()
    telegram.send_message.side_effect = TelegramAPIError("boom")

    webhook.deliver_reply(telegram, "42", "hi")

    telegram.send_message.assert_called_once_with("42", text="hi")


async def test_button_press_is_answered_before_agent_runs(approval_env):
    order = []
    approval_env.telegram.answer_callback_query.side_effect = lambda *a: order.append(
        "answer"
    )
    webhook.run_agent.side_effect = lambda *a, **k: order.append("run") or "result"

    await approval_env.call(callback_query("approve"))

    approval_env.telegram.answer_callback_query.assert_called_once_with("cb")
    assert order == ["answer", "run"]


async def test_button_press_is_answered_even_when_nothing_pending(approval_env):
    approval_env.pending_service.claim.return_value = None

    await approval_env.call(callback_query("approve"))

    approval_env.telegram.answer_callback_query.assert_called_once_with("cb")


async def test_failed_answer_does_not_block_the_decision(approval_env):
    approval_env.telegram.answer_callback_query.side_effect = TelegramAPIError("old")

    reply = await approval_env.call(callback_query("approve"))

    approval_env.state.approve.assert_called_once_with(approval_env.interruption)
    assert reply == "final"


async def test_decision_claims_pending_and_removes_buttons(approval_env):
    update = callback_query("approve")
    update.message = SimpleNamespace(message_id=7, chat=SimpleNamespace(id=42))

    await approval_env.call(update)

    approval_env.pending_service.claim.assert_awaited_once()
    approval_env.telegram.remove_inline_keyboard.assert_called_once_with("42", 7)


async def test_failed_button_removal_does_not_block_the_decision(approval_env):
    update = callback_query("approve")
    update.message = SimpleNamespace(message_id=7, chat=SimpleNamespace(id=42))
    approval_env.telegram.remove_inline_keyboard.side_effect = TelegramAPIError("x")

    reply = await approval_env.call(update)

    assert reply == "final"


async def test_failed_resume_restores_pending(approval_env):
    webhook.run_agent.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await approval_env.call(callback_query("approve"))

    approval_env.pending_service.save.assert_awaited_once()


async def test_message_while_decision_is_processing_does_not_run_agent():
    pending_service = Mock()
    pending_service.get = AsyncMock(
        return_value=PendingApproval(
            chat_session_id=uuid4(),
            run_state="s",
            user_item={},
            user_message_sequence=1,
            status="processing",
        )
    )
    patient_service = Mock()
    patient_service.get_patient_by_patient_ph_no = AsyncMock(
        return_value=SimpleNamespace(id=uuid4())
    )
    history = Mock()
    history.get_session = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    telegram = Mock()
    message = TelegramWebhookUpdate.model_validate(
        {"update_id": 1, "message": MESSAGE}
    ).message

    reply = await webhook.handle_message(
        message,
        patient_service,
        history,
        Mock(),
        pending_service,
        Mock(),
        telegram,
        Mock(),
    )

    assert "Still working" in reply
    telegram.send_message.assert_called_once_with("42", text=reply)
    history.add_message.assert_not_called()
