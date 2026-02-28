import json
from unittest.mock import patch


def _register(client):
    """Register a user and return the device token."""
    resp = client.post(
        "/api/auth/register",
        json={
            "invite_code": "FAMILY",
            "device_name": "Test iPhone",
            "platform": "ios",
            "display_name": "Tester",
        },
    )
    return resp.get_json()["device_token"]


def _mock_stream_chat(messages, system_prompt=None):
    """Fake Bedrock streaming: yields one text_delta then message_done."""
    yield {"type": "text_delta", "content": "Hello"}
    yield {
        "type": "message_done",
        "content": "Hello",
        "input_tokens": 10,
        "output_tokens": 5,
    }


def _parse_sse(data: bytes) -> list[dict]:
    """Parse SSE response bytes into a list of event dicts."""
    events = []
    for line in data.decode().strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


@patch("app.routes.chat.stream_chat", side_effect=_mock_stream_chat)
def test_chat_creates_conversation(mock_bedrock, client):
    token = _register(client)
    resp = client.post(
        "/api/chat",
        json={"message": "Hi there!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/event-stream")

    events = _parse_sse(resp.data)
    assert len(events) == 2
    assert events[0]["type"] == "text_delta"
    assert events[0]["content"] == "Hello"
    assert "conversation_id" in events[0]
    assert events[1]["type"] == "message_done"
    assert "message_id" in events[1]


@patch("app.routes.chat.stream_chat", side_effect=_mock_stream_chat)
def test_chat_continues_conversation(mock_bedrock, client):
    token = _register(client)

    # First message creates conversation
    resp1 = client.post(
        "/api/chat",
        json={"message": "Hello"},
        headers={"Authorization": f"Bearer {token}"},
    )
    events1 = _parse_sse(resp1.data)
    conv_id = events1[0]["conversation_id"]

    # Second message continues same conversation
    resp2 = client.post(
        "/api/chat",
        json={"message": "Follow up", "conversation_id": conv_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    events2 = _parse_sse(resp2.data)
    assert events2[0]["conversation_id"] == conv_id


@patch("app.routes.chat.stream_chat", side_effect=_mock_stream_chat)
def test_chat_requires_auth(mock_bedrock, client):
    resp = client.post("/api/chat", json={"message": "Hi"})
    assert resp.status_code == 401


def test_chat_requires_message(client):
    token = _register(client)
    resp = client.post(
        "/api/chat",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


@patch("app.routes.chat.stream_chat", side_effect=_mock_stream_chat)
def test_chat_invalid_conversation(mock_bedrock, client):
    token = _register(client)
    resp = client.post(
        "/api/chat",
        json={"message": "Hi", "conversation_id": "nonexistent"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
