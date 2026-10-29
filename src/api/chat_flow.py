from collections.abc import Awaitable, Callable

from src.api.agent_runtime import (
    NeedsApproval,
    RunOutcome,
    build_tool_context,
    messages_to_agent_items,
)
from src.api.agent_tools import ToolContext
from src.api.conversation import resolve_conversation
from src.api.dependencies import ChatServices
from src.api.models.chat_model import Decision
from src.api.models.chat_session_model import ChatMessage, SenderType
from src.api.models.patient_model import Patient
from src.api.models.pending_approval_model import PendingApproval
from src.api.models.telegram_model import CallbackQuery, Message
from src.api.telegram_delivery import (
    APPROVE,
    CHANGES_NEEDED,
    acknowledge_button_press,
    approval_prompt,
    deliver_reply,
    remove_buttons,
    typing_indicator,
)
from src.api.telemetry import set_span_attributes


async def finalize_run(
    outcome: RunOutcome,
    tool_context: ToolContext,
    user_item: dict,
    user_message_sequence: int,
    services: ChatServices,
    chat_id: str,
    stop_typing: Callable[[], Awaitable[None]] | None = None,
):
    """Persist a finished run, or save a paused one until the patient decides.

    Either way the reply is sent to the chat and also returned as the response.
    """
    chat_session_id = tool_context.chat_session_id

    if isinstance(outcome, NeedsApproval):
        await services.pending_approval_service.save(
            PendingApproval(
                chat_session_id=chat_session_id,
                run_state=outcome.state,
                user_item=user_item,
                user_message_sequence=user_message_sequence,
            )
        )
        prompt = approval_prompt(tool_context.patient_intake_state)
        if stop_typing is not None:
            await stop_typing()
        deliver_reply(services.telegram_client, chat_id, prompt)
        return prompt

    ai_message = ChatMessage(
        session_id=chat_session_id,
        sender_type=SenderType.bot,
        message_content=outcome.text,
        message_sequence=user_message_sequence + 1,
    )
    await services.chat_history_service.add_message(ai_message)

    await services.chat_history_service.add_agent_items(
        chat_session_id,
        [user_item] + outcome.items,
    )
    await services.pending_approval_service.delete(chat_session_id)

    # whatsapp_client.send_text_message(to=WHATSAPP_RECIPIENT_NUMBER, message=result.final_output)
    if stop_typing is not None:
        await stop_typing()
    deliver_reply(services.telegram_client, chat_id, outcome.text)

    return outcome.text


async def handle_message(message: Message, services: ChatServices):
    """Run the agent on a patient's chat message."""
    patient_ph_no = str(message.from_user.id)
    patient_message = message.text

    chat_history_service = services.chat_history_service
    patient, chat_session = await resolve_conversation(
        patient_ph_no, services.patient_service, chat_history_service
    )

    set_span_attributes(
        {"patient.id": str(patient.id), "chat_session.id": str(chat_session.id)}
    )

    # A run is paused (or its decision is being applied): don't start another one.
    pending = await services.pending_approval_service.get(chat_session.id)
    if pending and pending.status == "processing":
        reply = "Still working on your booking, one moment."
        deliver_reply(services.telegram_client, patient_ph_no, reply)
        return reply
    if pending:
        intake_state = await services.patient_intake_service.get_intake_state(
            chat_session.id
        )
        prompt = approval_prompt(intake_state)
        deliver_reply(services.telegram_client, patient_ph_no, prompt)
        return prompt

    previous_messages = await chat_history_service.get_session_messages(
        session_id=chat_session.id
    )

    user_message = ChatMessage(
        session_id=chat_session.id,
        sender_type=SenderType.patient,
        message_content=patient_message,
        message_sequence=(
            previous_messages[-1].message_sequence + 1 if previous_messages else 1
        ),
    )
    await chat_history_service.add_message(user_message)

    previous_items = await chat_history_service.get_agent_items(chat_session.id)
    if not previous_items and previous_messages:
        # Session predates agent item storage: seed it from the text transcript
        previous_items = messages_to_agent_items(previous_messages)
        await chat_history_service.add_agent_items(chat_session.id, previous_items)

    user_item = {"role": "user", "content": patient_message}
    tool_context = await build_tool_context(
        patient,
        chat_session.id,
        services.appointment_service,
        services.patient_intake_service,
    )

    async with typing_indicator(services.telegram_client, patient_ph_no) as stop_typing:
        outcome = await services.agent_runtime.run(
            previous_items, patient_message, tool_context
        )

        return await finalize_run(
            outcome,
            tool_context,
            user_item,
            user_message.message_sequence,
            services,
            patient_ph_no,
            stop_typing=stop_typing,
        )


async def handle_approval(callback_query: CallbackQuery, services: ChatServices):
    """Resume a paused run with the patient's Go Ahead / Changes needed decision."""
    # The press is answered only once the buttons are removed (or there is nothing
    # to remove), so the button's spinner stays until then. That must happen
    # before the agent run, which can outlast the query's validity.
    patient_ph_no = str(callback_query.from_user.id)
    telegram_client = services.telegram_client

    patient, chat_session = await resolve_conversation(
        patient_ph_no, services.patient_service, services.chat_history_service
    )
    session_id = chat_session.id
    set_span_attributes(
        {"patient.id": str(patient.id), "chat_session.id": str(session_id)}
    )

    decision = callback_query.data
    if decision not in (APPROVE, CHANGES_NEEDED):
        acknowledge_button_press(telegram_client, callback_query.id)
        if not await services.pending_approval_service.get(session_id):
            return "There is nothing waiting for your approval."
        intake_state = await services.patient_intake_service.get_intake_state(
            session_id
        )
        prompt = approval_prompt(intake_state)
        deliver_reply(telegram_client, patient_ph_no, prompt)
        return prompt

    # Claiming deletes the row, so a repeated press finds nothing and cannot
    # resume the same run twice.
    pending = await services.pending_approval_service.claim(session_id)
    if not pending:
        acknowledge_button_press(telegram_client, callback_query.id)
        return "There is nothing waiting for your approval."
    remove_buttons(telegram_client, callback_query)
    acknowledge_button_press(telegram_client, callback_query.id)

    try:
        return await resume_approval(pending, decision, patient, session_id, services)
    except Exception:
        # The decision wasn't applied: restore the prompt so it can be retried.
        await services.pending_approval_service.save(pending)
        raise


async def resume_approval(
    pending: PendingApproval,
    decision: str,
    patient: Patient,
    session_id,
    services: ChatServices,
):
    patient_ph_no = patient.patient_ph_no
    # The context isn't saved with the run state (services, UUIDs), so rebuild it.
    tool_context = await build_tool_context(
        patient,
        session_id,
        services.appointment_service,
        services.patient_intake_service,
    )
    decision = Decision.GO_AHEAD if decision == APPROVE else Decision.CHANGES_NEEDED

    async with typing_indicator(services.telegram_client, patient_ph_no) as stop_typing:
        outcome = await services.agent_runtime.resume(
            pending.run_state, tool_context, decision
        )

        return await finalize_run(
            outcome,
            tool_context,
            pending.user_item,
            pending.user_message_sequence,
            services,
            patient_ph_no,
            stop_typing=stop_typing,
        )
