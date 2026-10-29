"""Telegram adapter: parse messages and button presses, show typing, send the Reply."""

from src.api.chat_application import ChatApplication
from src.api.clients.telegram_client import TelegramClient
from src.api.dependencies import ChatServices
from src.api.models.chat_model import IncomingDecision, IncomingMessage
from src.api.models.telegram_model import CallbackQuery, Message
from src.api.telegram_delivery import (
    DECISION_FOR_CALLBACK,
    acknowledge_button_press,
    deliver_reply,
    remove_buttons,
    render_reply,
    typing_indicator,
)


def parse_message(message: Message) -> IncomingMessage:
    return IncomingMessage(sender_id=str(message.from_user.id), text=message.text)


async def run_message(
    message: Message, application: ChatApplication, telegram_client: TelegramClient
) -> str | dict:
    """Handle a Telegram message and send the Reply; returns it as the HTTP body.

    A failed send is logged by `deliver_reply`, not raised.
    """
    incoming = parse_message(message)
    async with typing_indicator(telegram_client, incoming.sender_id) as stop_typing:
        reply = await application.handle_message(incoming)
        await stop_typing()
    rendered = render_reply(reply)
    deliver_reply(telegram_client, incoming.sender_id, rendered)
    return rendered if reply.choices else reply.text


async def handle_message(message: Message, services: ChatServices) -> str | dict:
    return await run_message(
        message, services.chat_application, services.telegram_client
    )


def parse_callback(callback_query: CallbackQuery) -> IncomingDecision | None:
    """A button press as a Decision, or None for a callback value we don't know."""
    decision = DECISION_FOR_CALLBACK.get(callback_query.data)
    if decision is None:
        return None
    return IncomingDecision(
        sender_id=str(callback_query.from_user.id), decision=decision
    )


async def run_callback(
    callback_query: CallbackQuery,
    application: ChatApplication,
    telegram_client: TelegramClient,
) -> str | dict:
    """Handle a button press and send the Reply; returns it as the HTTP body."""
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
    rendered = render_reply(reply)
    deliver_reply(telegram_client, sender_id, rendered)
    return rendered if reply.choices else reply.text


async def handle_callback(
    callback_query: CallbackQuery, services: ChatServices
) -> str | dict:
    return await run_callback(
        callback_query, services.chat_application, services.telegram_client
    )
