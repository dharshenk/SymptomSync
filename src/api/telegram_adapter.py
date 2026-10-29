"""Telegram adapter: parse messages and button presses, show typing, send the Reply."""

from contextlib import asynccontextmanager
import asyncio
import logging

from src.api.chat_application import ChatApplication
from src.api.clients.telegram_client import TelegramAPIError, TelegramClient
from src.api.models.chat_model import (
    Decision,
    IncomingDecision,
    IncomingMessage,
    Reply,
)
from src.api.models.telegram_model import CallbackQuery, Message

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


def parse_message(message: Message) -> IncomingMessage:
    return IncomingMessage(sender_id=str(message.from_user.id), text=message.text)


async def handle_message(
    message: Message, application: ChatApplication, telegram_client: TelegramClient
) -> None:
    """Handle a Telegram message and send the Reply.

    A failed send is logged by `deliver_reply`, not raised.
    """
    incoming = parse_message(message)
    async with typing_indicator(telegram_client, incoming.sender_id) as stop_typing:
        reply = await application.handle_message(incoming)
        await stop_typing()
    deliver_reply(telegram_client, incoming.sender_id, render_reply(reply))


def parse_callback(callback_query: CallbackQuery) -> IncomingDecision | None:
    """A button press as a Decision, or None for a callback value we don't know."""
    decision = DECISION_FOR_CALLBACK.get(callback_query.data)
    if decision is None:
        return None
    return IncomingDecision(
        sender_id=str(callback_query.from_user.id), decision=decision
    )


async def handle_callback(
    callback_query: CallbackQuery,
    application: ChatApplication,
    telegram_client: TelegramClient,
) -> None:
    """Handle a button press and send the Reply."""
    sender_id = str(callback_query.from_user.id)
    decision = parse_callback(callback_query)
    # The press is answered once the buttons are gone, and both happen before
    # the run, which can outlast the query's validity. An unknown value is only
    # answered: its buttons may still belong to a live prompt.
    if decision is not None:
        remove_buttons(telegram_client, callback_query)
    acknowledge_button_press(telegram_client, callback_query.id)

    if decision is None:
        reply = await application.pending_prompt(sender_id)
    else:
        async with typing_indicator(telegram_client, sender_id) as stop_typing:
            reply = await application.handle_decision(decision)
            await stop_typing()
    deliver_reply(telegram_client, sender_id, render_reply(reply))
