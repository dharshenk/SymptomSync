"""
Telegram Bot Client for sending messages via the Telegram Bot API.
"""

import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pydantic import BaseModel, Field

from src.api.telemetry import traced


class TelegramConfig(BaseModel):
    """Telegram Bot API configuration"""

    bot_token: str
    base_url: str = Field(default="https://api.telegram.org")
    timeout: int = Field(default=30)
    max_retries: int = Field(default=3)

    @property
    def api_url(self) -> str:
        return f"{self.base_url}/bot{self.bot_token}"


class TelegramAPIError(Exception):
    """Custom exception for Telegram API errors"""

    def __init__(
        self,
        message: str,
        error_code: int | None = None,
        details: dict | None = None,
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class TelegramClient:
    """Telegram Bot Client"""

    def __init__(self, config: TelegramConfig):
        self.config = config
        self.logger = self._setup_logging()
        self.session = self._setup_session()

    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logger = logging.getLogger("telegram_client")
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def _setup_session(self) -> requests.Session:
        """Setup requests session with retry strategy"""
        session = requests.Session()

        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    @traced("telegram.answer_callback_query")
    def answer_callback_query(
        self, callback_query_id: str, text: str | None = None
    ) -> dict[str, Any]:
        """Acknowledge an inline button press so Telegram stops its loading spinner"""
        url = f"{self.config.api_url}/answerCallbackQuery"
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text is not None:
            payload["text"] = text

        return self._post(url, payload)

    @traced("telegram.remove_inline_keyboard")
    def remove_inline_keyboard(self, chat_id: str, message_id: int) -> dict[str, Any]:
        """Remove the inline buttons from a sent message"""
        url = f"{self.config.api_url}/editMessageReplyMarkup"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": {"inline_keyboard": []},
        }
        return self._post(url, payload)

    @traced("telegram.send_message")
    def send_message(
        self, chat_id: str, text: str, reply_markup: dict | None = None
    ) -> dict[str, Any]:
        """Send a text message to a Telegram chat, optionally with an inline keyboard"""
        url = f"{self.config.api_url}/sendMessage"
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        self.logger.info(f"Sending message to chat_id={chat_id}")

        result = self._post(url, payload)
        self.logger.info(
            f"Message sent successfully. message_id: {result.get('result', {}).get('message_id', 'unknown')}"
        )
        return result

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.session.post(
                url,
                json=payload,
                timeout=self.config.timeout,
            )

            response.raise_for_status()
            result = response.json()

            if not result.get("ok"):
                raise TelegramAPIError(
                    message=result.get("description", "Unknown API error"),
                    error_code=result.get("error_code"),
                    details=result,
                )

            return result

        except requests.exceptions.HTTPError as e:
            error_detail = {}
            try:
                error_detail = e.response.json()
            except (ValueError, AttributeError):
                pass

            raise TelegramAPIError(
                message=f"HTTP error {e.response.status_code}: {error_detail.get('description', str(e))}",
                error_code=e.response.status_code,
                details=error_detail,
            )

        except requests.exceptions.RequestException as e:
            raise TelegramAPIError(f"Request failed: {str(e)}")
