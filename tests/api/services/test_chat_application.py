"""ChatApplication.handle_message against a fake AgentRuntime and the real test_db."""

import pytest

from src.api.chat_application import STILL_WORKING, ChatApplication
from src.api.agent_runtime import Finished, NeedsApproval
from src.api.conversation import session_id_for
from src.api.models.chat_model import Decision, IncomingMessage
from src.api.models.chat_session_model import ChatMessage, SenderType
from tests.api.fake_agent_runtime import FakeAgentRuntime

SENDER = "chat-app-sender-1"
DOCTOR_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def doctor_id(monkeypatch):
    monkeypatch.setenv("DOCTOR_ID", DOCTOR_ID)


@pytest.fixture()
def make_app(
    patient_service,
    chat_history_service,
    patient_intake_service,
    pending_approval_service,
    appointment_service,
    db_client,
):
    created: list[str] = []

    def make(*outcomes) -> tuple[ChatApplication, FakeAgentRuntime]:
        runtime = FakeAgentRuntime(*outcomes)
        created.append(SENDER)
        return (
            ChatApplication(
                patient_service,
                chat_history_service,
                patient_intake_service,
                pending_approval_service,
                appointment_service,
                runtime,
            ),
            runtime,
        )

    yield make

    # Chat sessions cascade to messages, items, intake and pending approvals.
    for sender in created:
        db_client.execute_command(
            "DELETE FROM chat_sessions WHERE id = %(id)s;",
            {"id": str(session_id_for(sender))},
        )
        db_client.execute_command(
            "DELETE FROM patients WHERE patient_ph_no = %(ph)s;", {"ph": sender}
        )


async def test_finished_run_returns_reply_and_persists_the_exchange(
    make_app, chat_history_service, patient_intake_service
):
    app, runtime = make_app(Finished(text="Hello Pat", items=[{"type": "message"}]))

    reply = await app.handle_message(IncomingMessage(sender_id=SENDER, text="hi"))

    assert reply.text == "Hello Pat" and reply.choices == []
    session_id = session_id_for(SENDER)
    messages = await chat_history_service.get_session_messages(session_id)
    assert [(m.sender_type, m.message_content) for m in messages] == [
        (SenderType.patient, "hi"),
        (SenderType.bot, "Hello Pat"),
    ]
    assert await chat_history_service.get_agent_items(session_id) == [
        {"role": "user", "content": "hi"},
        {"type": "message"},
    ]
    # The tool context was built here: the Intake State exists and was handed over.
    assert await patient_intake_service.get_intake_state(session_id) is not None
    _, history, user_text, context = runtime.calls[0]
    assert history == [] and user_text == "hi"
    assert context.chat_session_id == session_id and str(context.doctor_id) == DOCTOR_ID


async def test_second_message_runs_on_the_stored_agent_items(make_app):
    app, runtime = make_app(
        Finished(text="one", items=[{"type": "message"}]),
        Finished(text="two", items=[]),
    )
    await app.handle_message(IncomingMessage(sender_id=SENDER, text="first"))

    await app.handle_message(IncomingMessage(sender_id=SENDER, text="second"))

    assert runtime.calls[1][1] == [
        {"role": "user", "content": "first"},
        {"type": "message"},
    ]


async def test_session_without_agent_items_is_seeded_from_the_transcript(
    make_app, patient_service, chat_history_service
):
    app, runtime = make_app(Finished(text="ok", items=[]))
    # An old session: text transcript only, no stored agent items.
    from src.api.conversation import resolve_conversation

    conversation = await resolve_conversation(
        SENDER, patient_service, chat_history_service
    )
    session_id = conversation.chat_session.id
    for sequence, (sender, text) in enumerate(
        [(SenderType.patient, "old question"), (SenderType.bot, "old answer")], 1
    ):
        await chat_history_service.add_message(
            ChatMessage(
                session_id=session_id,
                sender_type=sender,
                message_content=text,
                message_sequence=sequence,
            )
        )

    await app.handle_message(IncomingMessage(sender_id=SENDER, text="new"))

    assert runtime.calls[0][1] == [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
    ]


async def test_paused_run_saves_pending_approval_and_returns_the_prompt(
    make_app, pending_approval_service, chat_history_service
):
    app, _ = make_app(NeedsApproval(state="serialized"))

    reply = await app.handle_message(IncomingMessage(sender_id=SENDER, text="book"))

    assert [c.decision for c in reply.choices] == [
        Decision.GO_AHEAD,
        Decision.CHANGES_NEEDED,
    ]
    session_id = session_id_for(SENDER)
    pending = await pending_approval_service.get(session_id)
    assert pending.run_state == "serialized"
    assert pending.user_item == {"role": "user", "content": "book"}
    assert pending.user_message_sequence == 1
    # Only the patient's message is stored until the Decision arrives.
    messages = await chat_history_service.get_session_messages(session_id)
    assert [m.sender_type for m in messages] == [SenderType.patient]


async def test_message_while_pending_gets_the_prompt_again_without_a_run(
    make_app, pending_approval_service
):
    app, runtime = make_app(NeedsApproval(state="s"))
    await app.handle_message(IncomingMessage(sender_id=SENDER, text="book"))

    reply = await app.handle_message(IncomingMessage(sender_id=SENDER, text="hello?"))

    assert reply.choices and len(runtime.calls) == 1


async def test_message_while_decision_is_processing_gets_still_working(
    make_app, pending_approval_service
):
    app, runtime = make_app(NeedsApproval(state="s"))
    await app.handle_message(IncomingMessage(sender_id=SENDER, text="book"))
    await pending_approval_service.claim(session_id_for(SENDER))
    pending = await pending_approval_service.get(session_id_for(SENDER))
    assert pending.status == "processing"

    reply = await app.handle_message(IncomingMessage(sender_id=SENDER, text="hello?"))

    assert reply.text == STILL_WORKING and reply.choices == []
    assert len(runtime.calls) == 1
