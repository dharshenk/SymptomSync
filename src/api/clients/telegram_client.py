"""
Telegram Bot Client for sending messages via the Telegram Bot API.
"""

import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pydantic import BaseModel, Field


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

    def send_message(self, chat_id: str, text: str) -> dict[str, Any]:
        """Send a text message to a Telegram chat"""
        url = f"{self.config.api_url}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}

        self.logger.info(f"Sending message to chat_id={chat_id}")

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

            self.logger.info(
                f"Message sent successfully. message_id: {result.get('result', {}).get('message_id', 'unknown')}"
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
