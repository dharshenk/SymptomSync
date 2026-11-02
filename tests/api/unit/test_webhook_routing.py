"""POST /webhook routing and acknowledgement, with no database."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_chat_application, get_telegram_client
from src.api.models.chat_model import Reply
from src.api.whatsapp_webhook_api import router
from tests.api.unit.test_telegram_adapter import FakeApplication

USER = {"id": 42, "is_bot": False, "first_name": "Pat", "language_code": "en"}
CHAT = {"id": 42, "first_name": "Pat", "type": "private"}
MESSAGE = {"message_id": 1, "from": USER, "chat": CHAT, "date": 0, "text": "hi"}
PRESS = {"id": "cb", "from": USER, "data": "approve"}


@pytest.fixture()
def route():
    application = FakeApplication(Reply(text="ok"), [])
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_chat_application] = lambda: application
    app.dependency_overrides[get_telegram_client] = lambda: Mock()
    return TestClient(app), application


def test_message_goes_to_handle_message_and_is_acknowledged(route):
    client, application = route

    response = client.post("/webhook", json={"update_id": 1, "message": MESSAGE})

    assert response.json() == {"ok": True}
    assert len(application.received) == 1 and not application.decisions


def test_button_press_goes_to_handle_decision_and_is_acknowledged(route):
    client, application = route

    response = client.post("/webhook", json={"update_id": 1, "callback_query": PRESS})

    assert response.json() == {"ok": True}
    assert len(application.decisions) == 1 and not application.received


def test_update_with_neither_is_rejected(route):
    client, _ = route

    assert client.post("/webhook", json={"update_id": 1}).status_code == 422
