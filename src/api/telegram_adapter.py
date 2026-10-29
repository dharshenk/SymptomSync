"""Telegram adapter for Incoming Messages: parse, show typing, send the Reply."""

from src.api.chat_application import ChatApplication
from src.api.clients.telegram_client import TelegramClient
from src.api.dependencies import ChatServices
from src.api.models.chat_model import IncomingMessage
from src.api.models.telegram_model import Message
from src.api.telegram_delivery import deliver_reply, render_reply, typing_indicator


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
