from collections.abc import Awaitable, Callable

from src.api.agent_runtime import RunOutcome
from src.api.chat_application import (
    approval_prompt,
    build_tool_context,
    finalize_run as application_finalize_run,
)
from src.api.agent_tools import ToolContext
from src.api.conversation import resolve_conversation
from src.api.dependencies import ChatServices
from src.api.models.chat_model import Decision
from src.api.models.patient_model import Patient
from src.api.models.pending_approval_model import PendingApproval
from src.api.models.telegram_model import CallbackQuery
from src.api.telegram_delivery import (
    APPROVE,
    CHANGES_NEEDED,
    acknowledge_button_press,
    deliver_reply,
    remove_buttons,
    render_reply,
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
    """Persist the run (see chat_application), then send the reply and return it."""
    reply = await application_finalize_run(
        outcome,
        tool_context,
        user_item,
        user_message_sequence,
        services.chat_history_service,
        services.pending_approval_service,
    )
    if stop_typing is not None:
        await stop_typing()
    rendered = render_reply(reply)
    deliver_reply(services.telegram_client, chat_id, rendered)
    return rendered if reply.choices else reply.text


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
        prompt = render_reply(approval_prompt(intake_state))
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
