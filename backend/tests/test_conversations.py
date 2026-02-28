def _register_and_get_token(client):
    """Helper to register and return auth token."""
    reg = client.post(
        "/api/auth/register",
        json={
            "invite_code": "FAMILY",
            "device_name": "Test iPhone",
            "platform": "ios",
            "display_name": "Test User",
        },
    )
    return reg.get_json()["device_token"]


def test_list_conversations_empty(client):
    token = _register_and_get_token(client)
    response = client.get(
        "/api/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["conversations"] == []


def test_list_conversations_requires_auth(client):
    response = client.get("/api/conversations")
    assert response.status_code == 401


def test_delete_nonexistent_conversation(client):
    token = _register_and_get_token(client)
    response = client.delete(
        "/api/conversations/nonexistent",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


def test_get_messages_requires_auth(client):
    response = client.get("/api/conversations/test123/messages")
    assert response.status_code == 401
