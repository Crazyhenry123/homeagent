import json
from unittest.mock import MagicMock, patch


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
def test_chat_default_uses_bedrock(mock_bedrock, client):
    """By default (USE_AGENT_ORCHESTRATOR=false), chat uses stream_chat."""
    token = _register(client)
    resp = client.post(
        "/api/chat",
        json={"message": "Hi there!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.data)
    assert events[0]["type"] == "text_delta"
    assert events[0]["content"] == "Hello"
    mock_bedrock.assert_called_once()


def _mock_stream_agent_chat(
    messages, user_id, conversation_id=None, system_prompt=None, tools=None
):
    """Fake agent orchestrator streaming."""
    yield {"type": "text_delta", "content": "Agent "}
    yield {"type": "text_delta", "content": "reply"}
    yield {
        "type": "message_done",
        "content": "Agent reply",
        "input_tokens": 15,
        "output_tokens": 8,
    }


@patch(
    "app.services.agent_orchestrator.stream_agent_chat",
    side_effect=_mock_stream_agent_chat,
)
def test_chat_with_orchestrator_flag(mock_agent, app, client):
    """When USE_AGENT_ORCHESTRATOR=true, chat uses agent orchestrator."""
    app.config["USE_AGENT_ORCHESTRATOR"] = True

    token = _register(client)
    resp = client.post(
        "/api/chat",
        json={"message": "Hi there!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.data)
    text_events = [e for e in events if e["type"] == "text_delta"]
    assert len(text_events) == 2
    assert text_events[0]["content"] == "Agent "
    assert text_events[1]["content"] == "reply"
    done_events = [e for e in events if e["type"] == "message_done"]
    assert len(done_events) == 1


def test_build_system_prompt_with_profile(app):
    """Test that system prompt is personalized with profile data."""
    from app.services.agent_orchestrator import _build_system_prompt
    from app.services.profile import create_profile

    with app.app_context():
        profile = create_profile("test-user", "Alice", role="member")
        from app.services.profile import update_profile

        update_profile(
            "test-user",
            {
                "family_role": "Daughter",
                "interests": ["reading", "coding"],
                "health_notes": "Vegetarian",
            },
        )

        prompt = _build_system_prompt("test-user", "You are a helpful assistant.")
        assert "Alice" in prompt
        assert "Daughter" in prompt
        assert "reading" in prompt
        assert "coding" in prompt
        assert "Vegetarian" in prompt


def test_build_system_prompt_no_profile(app):
    """Test that system prompt falls back to base when no profile exists."""
    from app.services.agent_orchestrator import _build_system_prompt

    with app.app_context():
        base = "You are a helpful assistant."
        prompt = _build_system_prompt("nonexistent-user", base)
        assert prompt == base
