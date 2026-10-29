from contextlib import asynccontextmanager
import asyncio
import logging

from src.api.clients.telegram_client import TelegramAPIError, TelegramClient
from src.api.models.patient_intake_model import PatientIntakeState
from src.api.models.telegram_model import CallbackQuery

logger = logging.getLogger(__name__)

APPROVE = "approve"
CHANGES_NEEDED = "changes_needed"


@asynccontextmanager
async def typing_indicator(telegram_client: TelegramClient, chat_id: str):
    """Refresh the typing status while an agent run is in progress."""
    stopped = asyncio.Event()

    async def refresh():
        while not stopped.is_set():
            try:
                await asyncio.to_thread(telegram_client.send_typing_action, chat_id)
            except TelegramAPIError:
                logger.exception("Failed to send typing action to chat_id=%s", chat_id)
            try:
                await asyncio.wait_for(stopped.wait(), timeout=4)
            except asyncio.TimeoutError:
                pass

    task = asyncio.create_task(refresh())

    async def stop():
        stopped.set()
        await task

    try:
        await asyncio.sleep(0)
        yield stop
    finally:
        await stop()


def approval_prompt(intake_state: PatientIntakeState) -> dict:
    """Booking summary with Go Ahead / Changes needed buttons (Telegram format)."""
    details = [
        ("Name", intake_state.name),
        ("Age", intake_state.age),
        ("Gender", intake_state.gender),
        ("Symptoms", intake_state.symptoms),
        ("Pre-existing conditions", intake_state.pre_existing_conditions),
        ("Medications", intake_state.medications),
        (
            "Date",
            (
                intake_state.preferred_date.strftime("%A, %B %d, %Y")
                if intake_state.preferred_date
                else None
            ),
        ),
        (
            "Start time",
            (
                intake_state.preferred_start_time.strftime("%I:%M %p")
                if intake_state.preferred_start_time
                else None
            ),
        ),
    ]
    lines = [f"{label}: {value}" for label, value in details if value is not None]
    text = (
        "Please review your appointment details:\n\n"
        + "\n".join(lines)
        + "\n\nShall I go ahead and book it?"
    )
    return {
        "text": text,
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "Go Ahead", "callback_data": APPROVE}],
                [{"text": "Changes needed", "callback_data": CHANGES_NEEDED}],
            ]
        },
    }


def deliver_reply(telegram_client: TelegramClient, chat_id: str, reply: str | dict):
    """Push a reply to the chat; a dict is a prompt with `text` and `reply_markup`.

    A failed send is logged, not raised: the run is already persisted, and an
    error response would make Telegram redeliver the update and re-run the agent.
    """
    prompt = reply if isinstance(reply, dict) else {"text": reply}
    try:
        telegram_client.send_message(chat_id, **prompt)
    except TelegramAPIError:
        logger.exception("Failed to send Telegram reply to chat_id=%s", chat_id)


def acknowledge_button_press(telegram_client: TelegramClient, callback_query_id: str):
    """Stop the button's loading spinner (call after the buttons are removed); a failure is logged, not raised.

    Telegram only accepts this for a short time after the press, and the
    decision can still be processed without it.
    """
    try:
        telegram_client.answer_callback_query(callback_query_id)
    except TelegramAPIError:
        logger.exception("Failed to answer callback_query_id=%s", callback_query_id)


def remove_buttons(telegram_client: TelegramClient, callback_query: CallbackQuery):
    """Take the buttons off the pressed message; a failure is logged, not raised."""
    if callback_query.message is None:
        return
    try:
        telegram_client.remove_inline_keyboard(
            str(callback_query.message.chat.id), callback_query.message.message_id
        )
    except TelegramAPIError:
        logger.exception(
            "Failed to remove buttons from message_id=%s",
            callback_query.message.message_id,
        )
