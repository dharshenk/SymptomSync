"""
Integration tests for WhatsAppClient using real WhatsApp API credentials.
Environment variables required:
- WHATSAPP_ACCESS_TOKEN
- WHATSAPP_PHONE_NUMBER_ID
- WHATSAPP_RECIPIENT_NUMBER
"""

import os
import pytest
from src.api.clients.whatsapp_client import (
    WhatsAppClient,
    WhatsAppConfig,
    WhatsAppAPIError,
)
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(scope="module")
def whatsapp_client():
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    assert access_token, "WHATSAPP_ACCESS_TOKEN env var required"
    assert phone_number_id, "WHATSAPP_PHONE_NUMBER_ID env var required"
    config = WhatsAppConfig(
        access_token=access_token,
        phone_number_id=phone_number_id,
    )
    return WhatsAppClient(config)


@pytest.fixture(scope="module")
def recipient_number():
    number = os.environ.get("WHATSAPP_RECIPIENT_NUMBER")
    assert number, "WHATSAPP_RECIPIENT_NUMBER env var required"
    return number


def test_send_text_message(whatsapp_client, recipient_number):
    resp = whatsapp_client.send_text_message(
        recipient_number, "Integration test: Hello from pytest!"
    )
    assert "messages" in resp
    assert resp["messages"][0]["id"]


def test_send_template_message(whatsapp_client, recipient_number):
    # You must have a template approved in your WhatsApp Business account for this to work
    template_name = os.environ.get("WHATSAPP_TEMPLATE_NAME", "hello_world")
    try:
        resp = whatsapp_client.send_template_message(
            recipient_number,
            template_name=template_name,
            language_code="en_US",
            parameters=None,
        )
        assert "messages" in resp
        assert resp["messages"][0]["id"]
    except WhatsAppAPIError as e:
        # Template not found or not approved
        pytest.skip(f"Template message failed: {e}")


# def test_send_image_message(whatsapp_client, recipient_number):
#     # You must upload an image to WhatsApp Business and get a media_id
#     media_id = os.environ.get("WHATSAPP_IMAGE_MEDIA_ID")
#     if not media_id:
#         pytest.skip("No WHATSAPP_IMAGE_MEDIA_ID set for image test")
#     resp = whatsapp_client.send_image_message(
#         recipient_number, media_id, caption="Integration test image")
#     assert "messages" in resp
#     assert resp["messages"][0]["id"]


def test_send_button_message(whatsapp_client, recipient_number):
    buttons = [
        {"id": "btn1", "title": "Yes"},
        {"id": "btn2", "title": "No"},
    ]
    resp = whatsapp_client.send_button_message(
        recipient_number,
        body_text="Do you like integration tests?",
        buttons=buttons,
        header_text="Integration Test",
        footer_text="pytest",
    )
    assert "messages" in resp
    assert resp["messages"][0]["id"]
