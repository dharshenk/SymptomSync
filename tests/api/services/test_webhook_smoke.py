"""POST /webhook end to end: real ChatApplication and test_db, fake runtime and Telegram."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.agent_runtime import Finished, NeedsApproval
from src.api.chat_application import ChatApplication
from src.api.conversation import session_id_for
from src.api.dependencies import get_chat_application, get_telegram_client
from src.api.whatsapp_webhook_api import router
from tests.api.fake_agent_runtime import FakeAgentRuntime

SENDER = "987650001"
USER = {"id": int(SENDER), "is_bot": False, "first_name": "Pat", "language_code": "en"}
CHAT = {"id": 42, "first_name": "Pat", "type": "private"}


def text_update(text):
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "from": USER,
            "chat": CHAT,
            "date": 0,
            "text": text,
        },
    }


def press_update(data):
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cb-1",
            "from": USER,
            "data": data,
            "message": {"message_id": 7, "chat": CHAT, "date": 0},
        },
    }


@pytest.fixture(autouse=True)
def doctor_id(monkeypatch):
    monkeypatch.setenv("DOCTOR_ID", "11111111-1111-1111-1111-111111111111")


@pytest.fixture()
def smoke(
    patient_service,
    chat_history_service,
    patient_intake_service,
    pending_approval_service,
    appointment_service,
    db_client,
):
    runtime = FakeAgentRuntime(
        NeedsApproval(state="serialized"),
        Finished(text="Booked!", items=[]),
    )
    telegram = Mock()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_chat_application] = lambda: ChatApplication(
        patient_service,
        chat_history_service,
        patient_intake_service,
        pending_approval_service,
        appointment_service,
        runtime,
    )
    app.dependency_overrides[get_telegram_client] = lambda: telegram

    yield TestClient(app), telegram

    db_client.execute_command(
        "DELETE FROM chat_sessions WHERE id = %(id)s;",
        {"id": str(session_id_for(SENDER))},
    )
    db_client.execute_command(
        "DELETE FROM patients WHERE patient_ph_no = %(ph)s;", {"ph": SENDER}
    )


def test_message_then_button_press_sends_replies_and_acknowledges(smoke):
    client, telegram = smoke

    first = client.post("/webhook", json=text_update("book me in"))
    second = client.post("/webhook", json=press_update("approve"))

    assert first.json() == second.json() == {"ok": True}
    prompt, booked = telegram.send_message.call_args_list
    assert "Shall I go ahead" in prompt.kwargs["text"]
    assert "reply_markup" in prompt.kwargs
    assert booked.kwargs == {"text": "Booked!"}
    telegram.remove_inline_keyboard.assert_called_once_with("42", 7)
    telegram.answer_callback_query.assert_called_once_with("cb-1")


def test_update_with_neither_message_nor_button_press_is_rejected(smoke):
    client, _ = smoke

    assert client.post("/webhook", json={"update_id": 3}).status_code == 422
