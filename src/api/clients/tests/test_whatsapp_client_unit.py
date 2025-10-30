"""
Unit tests for WhatsAppClient and related classes with high coverage.
Mocks external requests and covers error handling, message building, and config logic.
"""

import pytest
from unittest.mock import patch, MagicMock
from src.api.clients.whatsapp_client import (
    WhatsAppClient,
    WhatsAppConfig,
    MessageBuilder,
    WhatsAppAPIError,
)


import requests


@pytest.fixture
def config():
    return WhatsAppConfig(
        access_token="dummy_token",
        phone_number_id="123456",
        api_version="v23.0",
        base_url="https://graph.facebook.com",
        timeout=10,
        max_retries=2,
    )


@pytest.fixture
def client(config):
    return WhatsAppClient(config)


def test_whatsapp_config_api_url(config):
    assert config.api_url == "https://graph.facebook.com/v23.0/123456/messages"


def test_text_message_builder():
    msg = MessageBuilder.text_message("123", "hello", preview_url=True)
    assert msg["type"] == "text"
    assert msg["text"]["body"] == "hello"
    assert msg["text"]["preview_url"] is True


def test_template_message_builder():
    params = [{"type": "body", "parameters": [{"type": "text", "text": "foo"}]}]
    msg = MessageBuilder.template_message("123", "my_template", parameters=params)
    assert msg["type"] == "template"
    assert msg["template"]["name"] == "my_template"
    assert msg["template"]["components"] == params


def test_image_message_builder():
    msg = MessageBuilder.image_message("123", "media_id", caption="caption")
    assert msg["type"] == "image"
    assert msg["image"]["id"] == "media_id"
    assert msg["image"]["caption"] == "caption"


def test_button_message_builder():
    buttons = [{"id": "b1", "title": "T1"}, {"id": "b2", "title": "T2"}]
    msg = MessageBuilder.button_message(
        "123", "body", buttons, header_text="header", footer_text="footer"
    )
    assert msg["type"] == "interactive"
    assert msg["interactive"]["type"] == "button"
    assert msg["interactive"]["body"]["text"] == "body"
    assert msg["interactive"]["header"]["text"] == "header"
    assert msg["interactive"]["footer"]["text"] == "footer"
    assert len(msg["interactive"]["action"]["buttons"]) == 2


def test_button_message_builder_max_buttons():
    buttons = [{"id": str(i), "title": f"T{i}"} for i in range(4)]
    with pytest.raises(ValueError):
        MessageBuilder.button_message("123", "body", buttons)


def test_whatsapp_api_error():
    err = WhatsAppAPIError("msg", error_code=400, details={"foo": "bar"})
    assert err.message == "msg"
    assert err.error_code == 400
    assert err.details["foo"] == "bar"


@patch("src.api.clients.whatsapp_client.requests.Session.post")
def test_send_text_message_success(mock_post, client):
    mock_post.return_value = MagicMock(status_code=200)
    mock_post.return_value.json.return_value = {"messages": [{"id": "msgid"}]}
    resp = client.send_text_message("123", "hello")
    assert resp["messages"][0]["id"] == "msgid"


@patch("src.api.clients.whatsapp_client.requests.Session.post")
def test_send_template_message_success(mock_post, client):
    mock_post.return_value = MagicMock(status_code=200)
    mock_post.return_value.json.return_value = {"messages": [{"id": "tid"}]}
    resp = client.send_template_message("123", "tpl")
    assert resp["messages"][0]["id"] == "tid"


@patch("src.api.clients.whatsapp_client.requests.Session.post")
def test_send_image_message_success(mock_post, client):
    mock_post.return_value = MagicMock(status_code=200)
    mock_post.return_value.json.return_value = {"messages": [{"id": "imgid"}]}
    resp = client.send_image_message("123", "mediaid", caption="cap")
    assert resp["messages"][0]["id"] == "imgid"


@patch("src.api.clients.whatsapp_client.requests.Session.post")
def test_send_button_message_success(mock_post, client):
    mock_post.return_value = MagicMock(status_code=200)
    mock_post.return_value.json.return_value = {"messages": [{"id": "btnid"}]}
    buttons = [{"id": "b1", "title": "T1"}]
    resp = client.send_button_message("123", "body", buttons)
    assert resp["messages"][0]["id"] == "btnid"


@patch("src.api.clients.whatsapp_client.requests.Session.post")
def test_api_error_response(mock_post, client):
    mock_post.return_value = MagicMock(status_code=400)
    mock_post.return_value.json.return_value = {
        "error": {"message": "fail", "code": 400}
    }
    with pytest.raises(WhatsAppAPIError) as e:
        client.send_text_message("123", "fail")
    assert "fail" in str(e.value)
    assert e.value.error_code == 400


@patch("src.api.clients.whatsapp_client.requests.Session.post")
def test_http_error(mock_post, client):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.exceptions.RequestException(
        "HTTP error"
    )
    mock_post.return_value = mock_resp
    with patch(
        "src.api.clients.whatsapp_client.requests.Session.post", return_value=mock_resp
    ):
        with pytest.raises(WhatsAppAPIError):
            client.send_text_message("123", "fail")


@patch("src.api.clients.whatsapp_client.requests.Session.post")
def test_request_exception(mock_post, client):
    mock_post.side_effect = requests.exceptions.RequestException("Request failed")
    with pytest.raises(WhatsAppAPIError):
        client.send_text_message("123", "fail")


def test_setup_logging(client):
    logger = client._setup_logging()
    assert logger.name == "whatsapp_client"
    assert logger.level == 20  # INFO


def test_setup_session(client):
    session = client._setup_session()
    assert hasattr(session, "post")


def test_get_headers(client):
    headers = client._get_headers()
    assert "Authorization" in headers
    assert headers["Content-Type"] == "application/json"
