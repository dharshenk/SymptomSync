from contextlib import asynccontextmanager
import asyncio
import logging

from src.api.clients.telegram_client import TelegramAPIError, TelegramClient
from src.api.models.chat_model import Decision, Reply
from src.api.models.telegram_model import CallbackQuery

logger = logging.getLogger(__name__)

APPROVE = "approve"
CHANGES_NEEDED = "changes_needed"
CALLBACK_FOR_DECISION = {
    Decision.GO_AHEAD: APPROVE,
    Decision.CHANGES_NEEDED: CHANGES_NEEDED,
}
DECISION_FOR_CALLBACK = {callback: d for d, callback in CALLBACK_FOR_DECISION.items()}


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


def render_reply(reply: Reply) -> dict:
    """A Reply as Telegram `send_message` arguments; choices become an inline keyboard."""
    rendered: dict = {"text": reply.text}
    if reply.choices:
        rendered["reply_markup"] = {
            "inline_keyboard": [
                [{"text": c.label, "callback_data": CALLBACK_FOR_DECISION[c.decision]}]
                for c in reply.choices
            ]
        }
    return rendered


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
