from unittest.mock import Mock

import pytest

from src.api.clients.telegram_client import TelegramClient, TelegramConfig


@pytest.fixture
def client():
    client = TelegramClient(TelegramConfig(bot_token="t"))
    client.session = Mock()
    client.session.post.return_value.json.return_value = {"ok": True, "result": {}}
    return client


def sent_payload(client):
    return client.session.post.call_args.kwargs["json"]


def test_send_message_omits_reply_markup_by_default(client):
    client.send_message("42", "hi")

    assert sent_payload(client) == {"chat_id": "42", "text": "hi"}


def test_send_message_includes_reply_markup(client):
    markup = {"inline_keyboard": [[{"text": "Go Ahead", "callback_data": "approve"}]]}

    client.send_message("42", "hi", reply_markup=markup)

    assert sent_payload(client)["reply_markup"] == markup
