"""Tests for chat media (image) upload — mocked S3."""

import json
from unittest.mock import MagicMock, patch


def _register(client):
    """Register a user and return (user_id, device_token)."""
    resp = client.post(
        "/api/auth/register",
        json={
            "invite_code": "FAMILY",
            "device_name": "Test iPhone",
            "platform": "ios",
            "display_name": "Tester",
        },
    )
    data = resp.get_json()
    return data["user_id"], data["device_token"]


def _with_s3_mock(app):
    """Set S3 config and return a mock S3 client."""
    app.config["S3_HEALTH_DOCUMENTS_BUCKET"] = "test-bucket"
    app.config["S3_ENDPOINT"] = "http://localhost:9000"
    mock_s3 = MagicMock()
    mock_s3.generate_presigned_url.return_value = "https://s3.example.com/presigned"
    return mock_s3


def test_upload_image_success(client, app):
    _, token = _register(client)
    mock_s3 = _with_s3_mock(app)

    with patch("app.services.chat_media._get_s3_client", return_value=mock_s3):
        resp = client.post(
            "/api/chat/upload-image",
            headers={"Authorization": f"Bearer {token}"},
            json={"content_type": "image/jpeg", "file_size": 1024},
        )

    assert resp.status_code == 201
    data = resp.get_json()
    assert "media_id" in data
    assert "upload_url" in data
    assert data["upload_url"] == "https://s3.example.com/presigned"


def test_upload_image_png(client, app):
    _, token = _register(client)
    mock_s3 = _with_s3_mock(app)

    with patch("app.services.chat_media._get_s3_client", return_value=mock_s3):
        resp = client.post(
            "/api/chat/upload-image",
            headers={"Authorization": f"Bearer {token}"},
            json={"content_type": "image/png", "file_size": 2048},
        )

    assert resp.status_code == 201


def test_upload_rejects_invalid_content_type(client, app):
    _, token = _register(client)
    _with_s3_mock(app)

    resp = client.post(
        "/api/chat/upload-image",
        headers={"Authorization": f"Bearer {token}"},
        json={"content_type": "text/plain", "file_size": 100},
    )
    assert resp.status_code == 400
    assert "Invalid content type" in resp.get_json()["error"]


def test_upload_rejects_oversized_file(client, app):
    _, token = _register(client)
    _with_s3_mock(app)

    resp = client.post(
        "/api/chat/upload-image",
        headers={"Authorization": f"Bearer {token}"},
        json={"content_type": "image/jpeg", "file_size": 10 * 1024 * 1024},
    )
    assert resp.status_code == 400
    assert "exceeds maximum" in resp.get_json()["error"]


def test_upload_rejects_zero_size(client, app):
    _, token = _register(client)
    _with_s3_mock(app)

    resp = client.post(
        "/api/chat/upload-image",
        headers={"Authorization": f"Bearer {token}"},
        json={"content_type": "image/jpeg", "file_size": 0},
    )
    assert resp.status_code == 400
    assert "positive" in resp.get_json()["error"]


def test_upload_requires_auth(client, app):
    resp = client.post(
        "/api/chat/upload-image",
        json={"content_type": "image/jpeg", "file_size": 1024},
    )
    assert resp.status_code == 401


def test_upload_missing_fields(client, app):
    _, token = _register(client)

    resp = client.post(
        "/api/chat/upload-image",
        headers={"Authorization": f"Bearer {token}"},
        json={"content_type": "image/jpeg"},
    )
    assert resp.status_code == 400
    assert "required" in resp.get_json()["error"]


def _mock_stream_chat(messages, system_prompt=None, images=None):
    """Fake Bedrock streaming: yields one text_delta then message_done."""
    yield {"type": "text_delta", "content": "I see an image"}
    yield {
        "type": "message_done",
        "content": "I see an image",
        "input_tokens": 100,
        "output_tokens": 10,
    }


def _parse_sse(data: bytes) -> list[dict]:
    events = []
    for line in data.decode().strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


@patch("app.routes.chat.stream_chat", side_effect=_mock_stream_chat)
def test_chat_with_media_ids(mock_bedrock, client, app):
    """Chat with media_ids resolves to S3 URIs and calls Bedrock."""
    user_id, token = _register(client)
    mock_s3 = _with_s3_mock(app)

    with patch("app.services.chat_media._get_s3_client", return_value=mock_s3):
        # Upload an image first
        upload_resp = client.post(
            "/api/chat/upload-image",
            headers={"Authorization": f"Bearer {token}"},
            json={"content_type": "image/jpeg", "file_size": 1024},
        )
        media_id = upload_resp.get_json()["media_id"]

        # Send chat with media
        resp = client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "message": "What's in this photo?",
                "media": [media_id],
            },
        )

    assert resp.status_code == 200
    events = _parse_sse(resp.data)
    assert events[0]["type"] == "text_delta"
    assert events[0]["content"] == "I see an image"


@patch("app.routes.chat.stream_chat", side_effect=_mock_stream_chat)
def test_chat_with_invalid_media_id(mock_bedrock, client, app):
    _, token = _register(client)

    resp = client.post(
        "/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "message": "What's in this photo?",
            "media": ["nonexistent-media-id"],
        },
    )
    assert resp.status_code == 400
    assert "not found" in resp.get_json()["error"]


@patch("app.routes.chat.stream_chat", side_effect=_mock_stream_chat)
def test_chat_with_too_many_media(mock_bedrock, client, app):
    user_id, token = _register(client)
    mock_s3 = _with_s3_mock(app)

    with patch("app.services.chat_media._get_s3_client", return_value=mock_s3):
        media_ids = []
        for _ in range(6):
            upload_resp = client.post(
                "/api/chat/upload-image",
                headers={"Authorization": f"Bearer {token}"},
                json={"content_type": "image/jpeg", "file_size": 1024},
            )
            media_ids.append(upload_resp.get_json()["media_id"])

        resp = client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "message": "Look at all these",
                "media": media_ids,
            },
        )

    assert resp.status_code == 400
    assert "Too many" in resp.get_json()["error"]
