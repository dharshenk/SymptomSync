"""Telegram adapter for Incoming Messages, against a fake Telegram client."""

from unittest.mock import Mock

import pytest

from src.api import telegram_adapter
from src.api.clients.telegram_client import TelegramAPIError
from src.api.models.chat_model import (
    Choice,
    Decision,
    IncomingDecision,
    IncomingMessage,
    Reply,
)
from src.api.models.telegram_model import TelegramWebhookUpdate

USER = {"id": 42, "is_bot": False, "first_name": "Pat", "language_code": "en"}
MESSAGE = TelegramWebhookUpdate.model_validate(
    {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "from": USER,
            "chat": {"id": 42, "first_name": "Pat", "type": "private"},
            "date": 0,
            "text": "hi",
        },
    }
).message


def press(data, with_message=True):
    callback = {"id": "cb-1", "from": USER, "data": data}
    if with_message:
        callback["message"] = {
            "message_id": 7,
            "chat": {"id": 42, "first_name": "Pat", "type": "private"},
            "date": 0,
        }
    return TelegramWebhookUpdate.model_validate(
        {"update_id": 2, "callback_query": callback}
    ).callback_query


class FakeApplication:
    def __init__(self, reply: Reply, events: list):
        self.reply = reply
        self.events = events
        self.received: list[IncomingMessage] = []
        self.decisions: list[IncomingDecision] = []
        self.prompted_for: list[str] = []

    async def handle_decision(self, decision):
        self.decisions.append(decision)
        self.events.append("run")
        return self.reply

    async def pending_prompt(self, sender_id):
        self.prompted_for.append(sender_id)
        return self.reply

    async def handle_message(self, message):
        self.received.append(message)
        self.events.append("run")
        return self.reply


def make_telegram(events: list) -> Mock:
    telegram = Mock()
    telegram.send_typing_action.side_effect = lambda chat_id: events.append("typing")
    telegram.send_message.side_effect = lambda *a, **k: events.append("send")
    telegram.remove_inline_keyboard.side_effect = lambda *a: events.append("unbutton")
    telegram.answer_callback_query.side_effect = lambda *a: events.append("ack")
    return telegram


def test_message_is_parsed_into_an_incoming_message():
    assert telegram_adapter.parse_message(MESSAGE) == IncomingMessage(
        sender_id="42", text="hi"
    )


async def test_typing_shows_during_the_run_and_the_reply_is_sent_afterwards():
    events: list = []
    app, telegram = FakeApplication(Reply(text="hello"), events), make_telegram(events)

    body = await telegram_adapter.run_message(MESSAGE, app, telegram)

    assert events == ["typing", "run", "send"]
    assert app.received == [IncomingMessage(sender_id="42", text="hi")]
    telegram.send_message.assert_called_once_with("42", text="hello")
    assert body == "hello"


async def test_choices_are_sent_as_an_inline_keyboard():
    reply = Reply(
        text="Review",
        choices=[
            Choice(label="Go Ahead", decision=Decision.GO_AHEAD),
            Choice(label="Changes needed", decision=Decision.CHANGES_NEEDED),
        ],
    )
    telegram = make_telegram([])

    await telegram_adapter.run_message(MESSAGE, FakeApplication(reply, []), telegram)

    markup = telegram.send_message.call_args.kwargs["reply_markup"]
    buttons = [b for row in markup["inline_keyboard"] for b in row]
    assert [(b["text"], b["callback_data"]) for b in buttons] == [
        ("Go Ahead", "approve"),
        ("Changes needed", "changes_needed"),
    ]


async def test_failed_send_is_logged_not_raised():
    telegram = make_telegram([])
    telegram.send_message.side_effect = TelegramAPIError("boom")

    body = await telegram_adapter.run_message(
        MESSAGE, FakeApplication(Reply(text="hello"), []), telegram
    )

    assert body == "hello"


@pytest.mark.parametrize(
    "data, expected",
    [("approve", Decision.GO_AHEAD), ("changes_needed", Decision.CHANGES_NEEDED)],
)
def test_button_callbacks_map_to_decisions(data, expected):
    assert telegram_adapter.parse_callback(press(data)) == IncomingDecision(
        sender_id="42", decision=expected
    )


@pytest.mark.parametrize("data", ["bogus", None])
def test_unknown_callback_maps_to_no_decision(data):
    assert telegram_adapter.parse_callback(press(data)) is None


async def test_press_removes_buttons_and_acks_before_the_run_then_replies():
    events: list = []
    app, telegram = FakeApplication(Reply(text="Booked"), events), make_telegram(events)

    body = await telegram_adapter.run_callback(press("approve"), app, telegram)

    assert events.index("unbutton") < events.index("ack") < events.index("run")
    assert events[-1] == "send"
    assert app.decisions == [
        IncomingDecision(sender_id="42", decision=Decision.GO_AHEAD)
    ]
    telegram.remove_inline_keyboard.assert_called_once_with("42", 7)
    telegram.answer_callback_query.assert_called_once_with("cb-1")
    telegram.send_message.assert_called_once_with("42", text="Booked")
    assert body == "Booked"


async def test_unknown_callback_acks_and_resends_the_prompt_without_a_decision():
    events: list = []
    app, telegram = FakeApplication(Reply(text="Review"), events), make_telegram(events)

    body = await telegram_adapter.run_callback(press("bogus"), app, telegram)

    assert app.decisions == [] and app.prompted_for == ["42"]
    assert "ack" in events and "run" not in events
    telegram.remove_inline_keyboard.assert_not_called()
    telegram.send_message.assert_called_once_with("42", text="Review")
    assert body == "Review"


async def test_press_still_runs_when_the_message_is_unavailable():
    app, telegram = FakeApplication(Reply(text="ok"), []), make_telegram([])

    await telegram_adapter.run_callback(
        press("approve", with_message=False), app, telegram
    )

    telegram.remove_inline_keyboard.assert_not_called()
    assert len(app.decisions) == 1


@pytest.mark.parametrize("failing", ["remove_inline_keyboard", "answer_callback_query"])
async def test_failed_button_removal_or_ack_does_not_block_the_decision(failing):
    app, telegram = FakeApplication(Reply(text="Booked"), []), make_telegram([])
    getattr(telegram, failing).side_effect = TelegramAPIError("too old")

    body = await telegram_adapter.run_callback(press("approve"), app, telegram)

    assert len(app.decisions) == 1 and body == "Booked"
