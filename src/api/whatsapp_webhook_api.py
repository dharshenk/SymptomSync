from typing import Annotated
from dotenv import load_dotenv
from fastapi import Depends, APIRouter, HTTPException
import os

from src.api.chat_flow import handle_approval, handle_message
from src.api.clients.whatsapp_client import WhatsAppClient, WhatsAppConfig
from src.api.dependencies import ChatServices, get_chat_services
from src.api.models.telegram_model import TelegramWebhookUpdate

load_dotenv()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_RECIPIENT_NUMBER = os.getenv("WHATSAPP_RECIPIENT_NUMBER")


def get_whatsapp_client():
    return WhatsAppClient(
        WhatsAppConfig(
            access_token=os.getenv("WHATSAPP_ACCESS_TOKEN"),
            phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID"),
        )
    )


router = APIRouter()


@router.post("/webhook")
async def telegram_webhook(
    update: TelegramWebhookUpdate,
    services: Annotated[ChatServices, Depends(get_chat_services)],
):
    """Single Telegram entry point: a button press resumes a paused run, a message starts one."""
    if update.callback_query:
        return await handle_approval(update.callback_query, services)
    if update.message:
        return await handle_message(update.message, services)
    raise HTTPException(
        status_code=422, detail="Expected a message or a callback_query"
    )


# @router.get("/webhook")
# async def verify(
#     mode: str = Query(None, alias="hub.mode"),
#     token: str = Query(None, alias="hub.verify_token"),
#     challenge: str = Query(None, alias="hub.challenge"),
# ):
#     if mode and token:
#         if mode == "subscribe" and token == VERIFY_TOKEN:  # however you load config
#             # logging.info("WEBHOOK_VERIFIED")
#             return PlainTextResponse(content=challenge, status_code=200)
#         else:
#             # logging.info("VERIFICATION_FAILED")
#             raise HTTPException(status_code=403, detail="Verification failed")
#     else:
#         # logging.info("MISSING_PARAMETER")
#         raise HTTPException(status_code=400, detail="Missing parameters")
