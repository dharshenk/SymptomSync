"""ChatApplication.handle_message against a fake AgentRuntime and the real test_db."""

from datetime import date, time

import pytest

from src.api.chat_application import (
    NEW_SESSION_REPLY,
    NOTHING_WAITING,
    STILL_WORKING,
    ChatApplication,
)
from src.api.agent_runtime import Finished, NeedsApproval
from src.api.conversation import session_id_for
from src.api.models.chat_model import Decision, IncomingDecision, IncomingMessage
from src.api.models.appointment_model import Appointment
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
            "DELETE FROM appointments WHERE patient_id IN "
            "(SELECT id FROM patients WHERE patient_ph_no = %(ph)s);",
            {"ph": sender},
        )
        db_client.execute_command(
            "DELETE FROM chat_sessions WHERE id = %(id)s OR patient_id IN "
            "(SELECT id FROM patients WHERE patient_ph_no = %(ph)s);",
            {"id": str(session_id_for(sender)), "ph": sender},
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


async def paused(app, text="book"):
    return await app.handle_message(IncomingMessage(sender_id=SENDER, text=text))


def decision(value: Decision) -> IncomingDecision:
    return IncomingDecision(sender_id=SENDER, decision=value)


async def test_go_ahead_resumes_the_saved_run_and_persists_the_exchange(
    make_app, pending_approval_service, chat_history_service
):
    app, runtime = make_app(
        NeedsApproval(state="serialized"),
        Finished(text="Booked!", items=[{"type": "tool_output"}]),
    )
    await paused(app)

    reply = await app.handle_decision(decision(Decision.GO_AHEAD))

    assert reply.text == "Booked!" and reply.choices == []
    _, state, context, resumed_with = runtime.calls[1]
    session_id = session_id_for(SENDER)
    assert (state, resumed_with) == ("serialized", Decision.GO_AHEAD)
    assert context.chat_session_id == session_id
    assert await pending_approval_service.get(session_id) is None
    messages = await chat_history_service.get_session_messages(session_id)
    assert [(m.sender_type, m.message_content) for m in messages] == [
        (SenderType.patient, "book"),
        (SenderType.bot, "Booked!"),
    ]
    assert await chat_history_service.get_agent_items(session_id) == [
        {"role": "user", "content": "book"},
        {"type": "tool_output"},
    ]


async def test_changes_needed_resumes_with_that_decision_and_asks_what_to_change(
    make_app, pending_approval_service
):
    app, runtime = make_app(
        NeedsApproval(state="s"), Finished(text="What should change?", items=[])
    )
    await paused(app)

    reply = await app.handle_decision(decision(Decision.CHANGES_NEEDED))

    assert runtime.calls[1][3] == Decision.CHANGES_NEEDED
    assert reply.text == "What should change?"
    assert await pending_approval_service.get(session_id_for(SENDER)) is None


async def test_repeated_decision_finds_nothing_and_does_not_resume_again(make_app):
    app, runtime = make_app(NeedsApproval(state="s"), Finished(text="Booked", items=[]))
    await paused(app)
    await app.handle_decision(decision(Decision.GO_AHEAD))

    reply = await app.handle_decision(decision(Decision.GO_AHEAD))

    assert reply.text == NOTHING_WAITING and reply.choices == []
    assert [call[0] for call in runtime.calls] == ["run", "resume"]


async def test_decision_with_nothing_pending_does_not_run_the_agent(make_app):
    app, runtime = make_app()

    reply = await app.handle_decision(decision(Decision.GO_AHEAD))

    assert reply.text == NOTHING_WAITING
    assert runtime.calls == []


async def test_failed_decision_restores_the_pending_approval_for_a_retry(
    make_app, pending_approval_service
):
    app, runtime = make_app(
        NeedsApproval(state="s"),
        RuntimeError("llm down"),
        Finished(text="Booked", items=[]),
    )
    await paused(app)

    with pytest.raises(RuntimeError):
        await app.handle_decision(decision(Decision.GO_AHEAD))

    pending = await pending_approval_service.get(session_id_for(SENDER))
    assert pending.status == "pending" and pending.run_state == "s"
    reply = await app.handle_decision(decision(Decision.GO_AHEAD))
    assert reply.text == "Booked"


async def test_prompt_is_resent_while_pending_and_absent_when_nothing_waits(
    make_app,
):
    app, runtime = make_app(NeedsApproval(state="s"))
    assert (await app.pending_prompt(SENDER)).text == NOTHING_WAITING
    await paused(app)

    reply = await app.pending_prompt(SENDER)

    assert [c.decision for c in reply.choices] == [
        Decision.GO_AHEAD,
        Decision.CHANGES_NEEDED,
    ]
    assert len(runtime.calls) == 1


async def test_decision_while_another_is_processing_gets_still_working(
    make_app, pending_approval_service
):
    app, runtime = make_app(NeedsApproval(state="s"))
    await paused(app)
    await pending_approval_service.claim(session_id_for(SENDER))

    reply = await app.handle_decision(decision(Decision.GO_AHEAD))

    assert reply.text == STILL_WORKING
    assert len(runtime.calls) == 1


# --- /new: start a new Chat Session -------------------------------------


async def test_new_session_starts_a_second_session_and_the_next_message_uses_it(
    make_app, chat_history_service, patient_service
):
    app, runtime = make_app(Finished(text="a", items=[]), Finished(text="b", items=[]))
    await app.handle_message(IncomingMessage(sender_id=SENDER, text="hi"))

    reply = await app.start_new_session(SENDER)

    assert reply.text == NEW_SESSION_REPLY and reply.choices == []
    await app.handle_message(IncomingMessage(sender_id=SENDER, text="again"))
    old_id = session_id_for(SENDER)
    new_id = runtime.calls[1][3].chat_session_id
    assert new_id != old_id
    patient = await patient_service.get_patient_by_patient_ph_no(SENDER)
    new_session = await chat_history_service.get_session(new_id)
    assert new_session.patient_id == patient.id
    assert new_session.session_status == "active"
    assert (await chat_history_service.get_session(old_id)).session_status != "active"


async def session_status(db_client, session_id):
    rows = db_client.execute_query(
        "SELECT session_status FROM chat_sessions WHERE id = %(id)s;",
        {"id": str(session_id)},
        fetch="one",
    )
    return rows[0]["session_status"]


async def chat_then_new(app):
    await app.handle_message(IncomingMessage(sender_id=SENDER, text="hi"))
    return await app.start_new_session(SENDER)


async def test_next_message_after_new_has_blank_history_and_intake(
    make_app, patient_intake_service
):
    app, runtime = make_app(Finished(text="a", items=[]), Finished(text="b", items=[]))
    await app.handle_message(IncomingMessage(sender_id=SENDER, text="hi"))
    await patient_intake_service.update_intake_state(
        session_id_for(SENDER), name="Pat", age=30
    )
    await app.start_new_session(SENDER)

    await app.handle_message(IncomingMessage(sender_id=SENDER, text="Sam"))

    _, history, text, context = runtime.calls[1]
    assert history == [] and text == "Sam"
    assert context.patient_intake_state.name is None
    assert context.patient_intake_state.age is None


async def test_next_message_after_new_sees_no_earlier_appointment(
    make_app, appointment_service, patient_service, sample_doctor
):
    app, runtime = make_app(Finished(text="a", items=[]), Finished(text="b", items=[]))
    await app.handle_message(IncomingMessage(sender_id=SENDER, text="hi"))
    patient = await patient_service.get_patient_by_patient_ph_no(SENDER)
    await appointment_service.book_appointment(
        Appointment(
            patient_id=patient.id,
            doctor_id=sample_doctor.id,
            chat_session_id=session_id_for(SENDER),
            appointment_date=date(2030, 1, 1),
            start_time=time(10, 0),
            end_time=time(10, 30),
        )
    )
    await app.handle_message(IncomingMessage(sender_id=SENDER, text="again"))
    assert runtime.calls[1][3].appointment is not None

    await app.start_new_session(SENDER)
    runtime.outcomes.append(Finished(text="c", items=[]))
    await app.handle_message(IncomingMessage(sender_id=SENDER, text="Sam"))

    assert runtime.calls[2][3].appointment is None


async def test_old_session_is_abandoned_when_intake_incomplete(make_app, db_client):
    app, _ = make_app(Finished(text="a", items=[]))
    await chat_then_new(app)

    assert await session_status(db_client, session_id_for(SENDER)) == "abandoned"


async def test_old_session_is_completed_when_intake_completed(
    make_app, db_client, patient_intake_service
):
    app, _ = make_app(Finished(text="a", items=[]))
    await app.handle_message(IncomingMessage(sender_id=SENDER, text="hi"))
    await patient_intake_service.update_intake_state(
        session_id_for(SENDER), status="completed"
    )

    await app.start_new_session(SENDER)

    assert await session_status(db_client, session_id_for(SENDER)) == "completed"


async def test_old_session_is_completed_when_an_appointment_was_booked(
    make_app, db_client, appointment_service, patient_service, sample_doctor
):
    app, _ = make_app(Finished(text="a", items=[]))
    await app.handle_message(IncomingMessage(sender_id=SENDER, text="hi"))
    patient = await patient_service.get_patient_by_patient_ph_no(SENDER)
    await appointment_service.book_appointment(
        Appointment(
            patient_id=patient.id,
            doctor_id=sample_doctor.id,
            chat_session_id=session_id_for(SENDER),
            appointment_date=date(2030, 1, 2),
            start_time=time(11, 0),
            end_time=time(11, 30),
        )
    )

    await app.start_new_session(SENDER)

    assert await session_status(db_client, session_id_for(SENDER)) == "completed"


async def test_new_discards_the_pending_approval_and_a_later_decision_does_nothing(
    make_app, pending_approval_service
):
    app, runtime = make_app(NeedsApproval(state="s"))
    await paused(app)

    await app.start_new_session(SENDER)

    assert await pending_approval_service.get(session_id_for(SENDER)) is None
    reply = await app.handle_decision(decision(Decision.GO_AHEAD))
    assert reply.text == NOTHING_WAITING and len(runtime.calls) == 1


async def test_new_for_a_patient_with_no_history_creates_a_session_and_replies(
    make_app, chat_history_service, patient_service
):
    app, _ = make_app()

    reply = await app.start_new_session(SENDER)

    assert reply.text == NEW_SESSION_REPLY
    patient = await patient_service.get_patient_by_patient_ph_no(SENDER)
    current = await chat_history_service.get_current_session(patient.id)
    assert current.id != session_id_for(SENDER)


async def test_repeated_new_works_and_messages_go_to_the_newest_session(
    make_app, chat_history_service, patient_service, db_client
):
    app, runtime = make_app(Finished(text="a", items=[]), Finished(text="b", items=[]))
    await app.start_new_session(SENDER)
    await app.start_new_session(SENDER)
    await app.start_new_session(SENDER)

    await app.handle_message(IncomingMessage(sender_id=SENDER, text="hi"))
    await app.handle_message(IncomingMessage(sender_id=SENDER, text="more"))

    patient = await patient_service.get_patient_by_patient_ph_no(SENDER)
    rows = db_client.execute_query(
        "SELECT id FROM chat_sessions WHERE patient_id = %(p)s "
        "AND session_status = 'active';",
        {"p": str(patient.id)},
        fetch="all",
    )
    assert len(rows) == 1
    active = str(rows[0]["id"])
    assert [str(c[3].chat_session_id) for c in runtime.calls] == [active, active]


async def test_legacy_session_is_used_until_new_is_sent(make_app, chat_history_service):
    app, runtime = make_app(Finished(text="a", items=[]))

    await app.handle_message(IncomingMessage(sender_id=SENDER, text="hi"))

    assert runtime.calls[0][3].chat_session_id == session_id_for(SENDER)


async def test_old_messages_and_intake_state_remain_after_new(
    make_app, chat_history_service, patient_intake_service
):
    app, _ = make_app(Finished(text="a", items=[]))
    await app.handle_message(IncomingMessage(sender_id=SENDER, text="hi"))
    await patient_intake_service.update_intake_state(session_id_for(SENDER), name="Pat")

    await app.start_new_session(SENDER)

    old = session_id_for(SENDER)
    messages = await chat_history_service.get_session_messages(old)
    assert [m.message_content for m in messages] == ["hi", "a"]
    assert (await patient_intake_service.get_intake_state(old)).name == "Pat"
