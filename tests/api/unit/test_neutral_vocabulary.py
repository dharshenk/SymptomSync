"""Channel-neutral vocabulary and the configured doctor ID."""

import uuid

import pytest

from src.api import agent_runtime
from src.api.models.chat_model import Choice, Decision, Reply


def test_reply_is_plain_text_unless_it_has_choices():
    assert Reply(text="hi").choices == []

    prompt = Reply(
        text="Book it?",
        choices=[
            Choice(label="Go Ahead", decision=Decision.GO_AHEAD),
            Choice(label="Changes needed", decision=Decision.CHANGES_NEEDED),
        ],
    )
    assert [c.decision for c in prompt.choices] == [
        Decision.GO_AHEAD,
        Decision.CHANGES_NEEDED,
    ]


def test_doctor_id_comes_from_configuration(monkeypatch):
    doctor_id = "22222222-2222-2222-2222-222222222222"
    monkeypatch.setenv("DOCTOR_ID", doctor_id)

    assert agent_runtime.get_doctor_id() == uuid.UUID(doctor_id)


def test_missing_doctor_id_fails_loudly(monkeypatch):
    monkeypatch.delenv("DOCTOR_ID", raising=False)

    with pytest.raises(RuntimeError, match="DOCTOR_ID"):
        agent_runtime.get_doctor_id()
