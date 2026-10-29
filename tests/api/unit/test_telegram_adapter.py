"""Telegram adapter for Incoming Messages, against a fake Telegram client."""

from unittest.mock import Mock

from src.api import telegram_adapter
from src.api.clients.telegram_client import TelegramAPIError
from src.api.models.chat_model import Choice, Decision, IncomingMessage, Reply
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


class FakeApplication:
    def __init__(self, reply: Reply, events: list):
        self.reply = reply
        self.events = events
        self.received: list[IncomingMessage] = []

    async def handle_message(self, message):
        self.received.append(message)
        self.events.append("run")
        return self.reply


def make_telegram(events: list) -> Mock:
    telegram = Mock()
    telegram.send_typing_action.side_effect = lambda chat_id: events.append("typing")
    telegram.send_message.side_effect = lambda *a, **k: events.append("send")
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
