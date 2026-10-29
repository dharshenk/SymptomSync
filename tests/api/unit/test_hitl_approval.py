"""Human-in-the-loop approval for book_appointment and the /webhook dispatcher."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from src.api import chat_application, telegram_delivery
from src.api.agent_runtime import Finished, NeedsApproval
from src.api import whatsapp_webhook_api as webhook
from src.api.agent_tools.book_appointment import book_appointment
from src.api.clients.telegram_client import TelegramAPIError
from src.api.models.chat_model import Decision
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
    prompt = telegram_delivery.render_reply(
        chat_application.approval_prompt(make_context(**FULL).patient_intake_state)
    )

    assert "Test Patient" in prompt["text"] and "09:00 AM" in prompt["text"]
    buttons = [b for row in prompt["reply_markup"]["inline_keyboard"] for b in row]
    assert [b["callback_data"] for b in buttons] == ["approve", "changes_needed"]


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


MESSAGE = {
    "message_id": 1,
    "from": USER,
    "chat": {"id": 42, "first_name": "Pat", "type": "private"},
    "date": 0,
    "text": "hi",
}


async def dispatch(monkeypatch, payload):
    handle_callback = AsyncMock(return_value="approval")
    handle_message = AsyncMock(return_value="message")
    monkeypatch.setattr(webhook, "handle_callback", handle_callback)
    monkeypatch.setattr(webhook, "handle_message", handle_message)
    reply = await webhook.telegram_webhook(
        TelegramWebhookUpdate.model_validate({"update_id": 1, **payload}),
        Mock(),
    )
    return reply, handle_callback, handle_message


async def test_webhook_routes_button_press_to_approval(monkeypatch):
    payload = {"callback_query": {"id": "cb", "from": USER, "data": "approve"}}

    reply, handle_callback, handle_message = await dispatch(monkeypatch, payload)

    assert reply == "approval"
    handle_callback.assert_awaited_once()
    handle_message.assert_not_called()


async def test_webhook_routes_text_message_to_agent(monkeypatch):
    reply, handle_callback, handle_message = await dispatch(
        monkeypatch, {"message": MESSAGE}
    )

    assert reply == "message"
    handle_message.assert_awaited_once()
    handle_callback.assert_not_called()


async def test_webhook_rejects_update_with_neither(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await dispatch(monkeypatch, {})
    assert exc.value.status_code == 422


def test_deliver_reply_swallows_telegram_errors():
    telegram = Mock()
    telegram.send_message.side_effect = TelegramAPIError("boom")

    telegram_delivery.deliver_reply(telegram, "42", "hi")

    telegram.send_message.assert_called_once_with("42", text="hi")


async def test_typing_indicator_refreshes_and_stops(monkeypatch):
    telegram = Mock()
    sent = asyncio.Event()
    calls = []
    loop = asyncio.get_running_loop()

    def send_action(chat_id):
        calls.append(chat_id)
        if len(calls) == 2:
            loop.call_soon_threadsafe(sent.set)

    telegram.send_typing_action.side_effect = send_action
    original_wait_for = asyncio.wait_for

    async def fast_wait(awaitable, timeout):
        return await original_wait_for(awaitable, timeout=0.01)

    monkeypatch.setattr(asyncio, "wait_for", fast_wait)
    async with telegram_delivery.typing_indicator(telegram, "42"):
        await original_wait_for(sent.wait(), timeout=1)
    assert calls == ["42", "42"]
    await asyncio.sleep(0.03)
    assert calls == ["42", "42"]


async def test_typing_indicator_failure_does_not_fail_run():
    telegram = Mock()
    telegram.send_typing_action.side_effect = TelegramAPIError("unavailable")

    async with telegram_delivery.typing_indicator(telegram, "42"):
        pass

    telegram.send_typing_action.assert_called_once_with("42")
