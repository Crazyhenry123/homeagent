def _register_admin(client):
    """Register an admin user and return (token, user_id)."""
    resp = client.post(
        "/api/auth/register",
        json={
            "invite_code": "FAMILY",
            "device_name": "Admin Phone",
            "platform": "ios",
            "display_name": "Admin User",
        },
    )
    data = resp.get_json()
    return data["device_token"], data["user_id"]


def _register_member(client, admin_token):
    """Generate an invite code and register a member, return (token, user_id)."""
    code_resp = client.post(
        "/api/admin/invite-codes",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    code = code_resp.get_json()["code"]
    resp = client.post(
        "/api/auth/register",
        json={
            "invite_code": code,
            "device_name": "Member Phone",
            "platform": "android",
            "display_name": "Member User",
        },
    )
    data = resp.get_json()
    return data["device_token"], data["user_id"]


def test_list_agent_types(client):
    token, _ = _register_admin(client)
    resp = client.get(
        "/api/admin/agents/types",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "health_advisor" in data["agent_types"]
    assert "logistics_assistant" in data["agent_types"]
    assert "shopping_assistant" in data["agent_types"]


def test_enable_agent_for_user(client):
    admin_token, _ = _register_admin(client)
    _, member_id = _register_member(client, admin_token)

    resp = client.put(
        f"/api/admin/agents/{member_id}/health_advisor",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["agent_type"] == "health_advisor"
    assert data["enabled"] is True
    assert data["config"]["safety_disclaimers"] is True


def test_configure_agent_with_custom_config(client):
    admin_token, _ = _register_admin(client)
    _, member_id = _register_member(client, admin_token)

    resp = client.put(
        f"/api/admin/agents/{member_id}/health_advisor",
        json={
            "enabled": True,
            "config": {"web_search_enabled": False},
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    # Custom config merges with defaults
    assert data["config"]["safety_disclaimers"] is True
    assert data["config"]["web_search_enabled"] is False


def test_list_user_agents(client):
    admin_token, _ = _register_admin(client)
    _, member_id = _register_member(client, admin_token)

    # Enable two agents
    client.put(
        f"/api/admin/agents/{member_id}/health_advisor",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    client.put(
        f"/api/admin/agents/{member_id}/shopping_assistant",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    resp = client.get(
        f"/api/admin/agents/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    configs = resp.get_json()["agent_configs"]
    # Default agents (health_advisor, logistics_assistant) are auto-enabled,
    # plus we explicitly enabled shopping_assistant above.
    types = {c["agent_type"] for c in configs}
    assert {"health_advisor", "shopping_assistant", "logistics_assistant"}.issubset(types)


def test_disable_agent(client):
    admin_token, _ = _register_admin(client)
    _, member_id = _register_member(client, admin_token)

    # health_advisor is auto-enabled as a default agent; delete it
    resp = client.delete(
        f"/api/admin/agents/{member_id}/health_advisor",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    # Verify health_advisor is gone (logistics_assistant remains as default)
    resp = client.get(
        f"/api/admin/agents/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    types = {c["agent_type"] for c in resp.get_json()["agent_configs"]}
    assert "health_advisor" not in types


def test_delete_nonexistent_agent(client):
    admin_token, _ = _register_admin(client)
    _, member_id = _register_member(client, admin_token)

    # shopping_assistant is not a default agent, so it should not exist yet
    resp = client.delete(
        f"/api/admin/agents/{member_id}/shopping_assistant",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


def test_invalid_agent_type(client):
    admin_token, _ = _register_admin(client)
    _, member_id = _register_member(client, admin_token)

    resp = client.put(
        f"/api/admin/agents/{member_id}/nonexistent_agent",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400
    assert "Unknown agent type" in resp.get_json()["error"]


def test_member_cannot_manage_agents(client):
    admin_token, _ = _register_admin(client)
    member_token, member_id = _register_member(client, admin_token)

    resp = client.get(
        f"/api/admin/agents/{member_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403


def test_agent_types_requires_admin(client):
    admin_token, _ = _register_admin(client)
    member_token, _ = _register_member(client, admin_token)

    resp = client.get(
        "/api/admin/agents/types",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403
