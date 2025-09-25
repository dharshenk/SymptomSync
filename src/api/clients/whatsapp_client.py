"""
Production WhatsApp Client using Facebook Graph API v23.0
Supports: Text, Template, Image, and Interactive Button Messages
"""

import json
import logging
from typing import Any
from enum import Enum
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pydantic import BaseModel, Field


class WhatsAppConfig(BaseModel):
    """WhatsApp API configuration"""

    access_token: str
    phone_number_id: str
    api_version: str = Field(default="v23.0")
    base_url: str = Field(default="https://graph.facebook.com")
    timeout: int = Field(default=30)
    max_retries: int = Field(default=3)

    @property
    def api_url(self) -> str:
        return f"{self.base_url}/{self.api_version}/{self.phone_number_id}/messages"


class MessageType(Enum):
    """Supported message types"""

    TEXT = "text"
    TEMPLATE = "template"
    IMAGE = "image"
    INTERACTIVE = "interactive"


class InteractiveType(Enum):
    """Interactive message types"""

    BUTTON = "button"
    LIST = "list"


# Exceptions
class WhatsAppAPIError(Exception):
    """Custom exception for WhatsApp API errors"""

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


# Message builders
class MessageBuilder:
    """Helper class to build different message types"""

    @staticmethod
    def text_message(to: str, body: str, preview_url: bool = False) -> dict[str, Any]:
        """Build a text message"""
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": preview_url, "body": body},
        }

    @staticmethod
    def template_message(
        to: str,
        template_name: str,
        language_code: str = "en_US",
        parameters: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Build a template message"""
        message = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": {"name": template_name, "language": {"code": language_code}},
        }

        if parameters:
            message["template"]["components"] = parameters

        return message

    @staticmethod
    def image_message(
        to: str, media_id: str, caption: str | None = None
    ) -> dict[str, Any]:
        """Build an image message"""
        message = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": {"id": media_id},
        }

        if caption:
            message["image"]["caption"] = caption

        return message

    @staticmethod
    def button_message(
        to: str,
        body_text: str,
        buttons: list[dict[str, str]],
        header_text: str | None = None,
        footer_text: str | None = None,
    ) -> dict[str, Any]:
        """
        Build an interactive button message
        buttons format: [{"id": "button_id", "title": "Button Title"}, ...]
        """
        if len(buttons) > 3:
            raise ValueError("Maximum 3 buttons allowed")

        interactive_buttons = []
        for button in buttons:
            interactive_buttons.append(
                {
                    "type": "reply",
                    "reply": {"id": button["id"], "title": button["title"]},
                }
            )

        message = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {"buttons": interactive_buttons},
            },
        }

        if header_text:
            message["interactive"]["header"] = {"type": "text", "text": header_text}

        if footer_text:
            message["interactive"]["footer"] = {"text": footer_text}

        return message


# Main WhatsApp Client
class WhatsAppClient:
    """Production WhatsApp Client"""

    def __init__(self, config: WhatsAppConfig):
        self.config = config
        self.logger = self._setup_logging()
        self.session = self._setup_session()

    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logger = logging.getLogger("whatsapp_client")
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

    def _get_headers(self) -> dict[str, str]:
        """Get request headers"""
        return {
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/json",
        }

    def _make_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Make API request with error handling"""
        headers = self._get_headers()

        self.logger.info(f"Sending message to {payload.get('to', 'unknown')}")
        self.logger.debug(f"Payload: {json.dumps(payload, indent=2)}")

        try:
            response = self.session.post(
                self.config.api_url,
                headers=headers,
                json=payload,
                timeout=self.config.timeout,
            )

            response.raise_for_status()
            result = response.json()

            # Check for API-level errors
            if "error" in result:
                raise WhatsAppAPIError(
                    message=result["error"].get("message", "Unknown API error"),
                    error_code=result["error"].get("code"),
                    details=result["error"],
                )

            self.logger.info(
                f"Message sent successfully. ID: {result.get('messages', [{}])[0].get('id', 'unknown')}"
            )
            return result

        except requests.exceptions.HTTPError as e:
            error_detail = {}
            try:
                error_detail = e.response.json()
            except (ValueError, AttributeError):
                pass

            raise WhatsAppAPIError(
                message=f"HTTP error {e.response.status_code}: {error_detail.get('error', {}).get('message', str(e))}",
                error_code=e.response.status_code,
                details=error_detail,
            )

        except requests.exceptions.RequestException as e:
            raise WhatsAppAPIError(f"Request failed: {str(e)}")

    def send_text_message(
        self, to: str, message: str, preview_url: bool = False
    ) -> dict[str, Any]:
        """Send a text message"""
        payload = MessageBuilder.text_message(to, message, preview_url)
        return self._make_request(payload)

    def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "en_US",
        parameters: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Send a template message"""
        payload = MessageBuilder.template_message(
            to, template_name, language_code, parameters
        )
        return self._make_request(payload)

    def send_image_message(
        self, to: str, media_id: str, caption: str | None = None
    ) -> dict[str, Any]:
        """Send an image message"""
        payload = MessageBuilder.image_message(to, media_id, caption)
        return self._make_request(payload)

    def send_button_message(
        self,
        to: str,
        body_text: str,
        buttons: list[dict[str, str]],
        header_text: str | None = None,
        footer_text: str | None = None,
    ) -> dict[str, Any]:
        """Send an interactive button message"""
        payload = MessageBuilder.button_message(
            to, body_text, buttons, header_text, footer_text
        )
        return self._make_request(payload)
