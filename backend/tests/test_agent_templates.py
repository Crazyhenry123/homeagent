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


# --- Template CRUD tests (admin) ---


def test_seed_builtin_templates(client):
    """Built-in templates (health_advisor, etc.) are auto-created on startup."""
    token, _ = _register_admin(client)
    resp = client.get(
        "/api/admin/agent-templates",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    templates = resp.get_json()["templates"]
    types = {t["agent_type"] for t in templates}
    assert "health_advisor" in types
    assert "logistics_assistant" in types
    assert "shopping_assistant" in types
    for t in templates:
        assert t["is_builtin"] is True
        assert t["available_to"] == "all"


def test_create_template(client):
    """Admin can create a custom agent template."""
    token, _ = _register_admin(client)
    resp = client.post(
        "/api/admin/agent-templates",
        json={
            "name": "Meal Planner",
            "agent_type": "meal_planner",
            "description": "Plans weekly meals for the family",
            "system_prompt": "You are a meal planning assistant.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["agent_type"] == "meal_planner"
    assert data["name"] == "Meal Planner"
    assert data["is_builtin"] is False
    assert data["template_id"]


def test_create_duplicate_agent_type(client):
    """Duplicate agent_type is rejected."""
    token, _ = _register_admin(client)
    client.post(
        "/api/admin/agent-templates",
        json={
            "name": "Meal Planner",
            "agent_type": "meal_planner",
            "description": "Plans meals",
            "system_prompt": "You plan meals.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = client.post(
        "/api/admin/agent-templates",
        json={
            "name": "Meal Planner 2",
            "agent_type": "meal_planner",
            "description": "Also plans meals",
            "system_prompt": "You also plan meals.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "already exists" in resp.get_json()["error"]


def test_update_template(client):
    """Admin can update a custom template's fields."""
    token, _ = _register_admin(client)
    create_resp = client.post(
        "/api/admin/agent-templates",
        json={
            "name": "Meal Planner",
            "agent_type": "meal_planner",
            "description": "Plans meals",
            "system_prompt": "You plan meals.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    template_id = create_resp.get_json()["template_id"]

    resp = client.put(
        f"/api/admin/agent-templates/{template_id}",
        json={"name": "Weekly Meal Planner", "description": "Plans weekly meals"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["name"] == "Weekly Meal Planner"
    assert data["description"] == "Plans weekly meals"


def test_delete_builtin_rejected(client):
    """Cannot delete a built-in agent template."""
    token, _ = _register_admin(client)
    resp = client.get(
        "/api/admin/agent-templates",
        headers={"Authorization": f"Bearer {token}"},
    )
    builtin = [t for t in resp.get_json()["templates"] if t["is_builtin"]]
    assert len(builtin) > 0

    resp = client.delete(
        f"/api/admin/agent-templates/{builtin[0]['template_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "Cannot delete built-in" in resp.get_json()["error"]


def test_delete_custom_cascades_configs(client):
    """Deleting a custom template removes related AgentConfigs."""
    admin_token, _ = _register_admin(client)
    _, member_id = _register_member(client, admin_token)

    # Create a custom template
    create_resp = client.post(
        "/api/admin/agent-templates",
        json={
            "name": "Meal Planner",
            "agent_type": "meal_planner",
            "description": "Plans meals",
            "system_prompt": "You plan meals.",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    template_id = create_resp.get_json()["template_id"]

    # Enable it for the member
    client.put(
        f"/api/admin/agents/{member_id}/meal_planner",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Verify config exists
    resp = client.get(
        f"/api/admin/agents/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert any(
        c["agent_type"] == "meal_planner"
        for c in resp.get_json()["agent_configs"]
    )

    # Delete the template
    resp = client.delete(
        f"/api/admin/agent-templates/{template_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200

    # Verify config is gone
    resp = client.get(
        f"/api/admin/agents/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert not any(
        c["agent_type"] == "meal_planner"
        for c in resp.get_json()["agent_configs"]
    )


def test_create_template_missing_fields(client):
    """Creating a template with missing required fields returns 400."""
    token, _ = _register_admin(client)
    resp = client.post(
        "/api/admin/agent-templates",
        json={"name": "Incomplete"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "Missing required fields" in resp.get_json()["error"]


# --- Availability tests ---


def test_available_to_all(client):
    """Template with available_to='all' is visible to all members."""
    admin_token, _ = _register_admin(client)
    member_token, _ = _register_member(client, admin_token)

    # Built-in templates are available_to='all' by default
    resp = client.get(
        "/api/agents/available",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 200
    agents = resp.get_json()["agents"]
    types = {a["agent_type"] for a in agents}
    assert "health_advisor" in types


def test_available_to_specific(client):
    """Template restricted to specific user_ids is only visible to them."""
    admin_token, admin_id = _register_admin(client)
    member_token, member_id = _register_member(client, admin_token)

    # Create template available only to admin
    client.post(
        "/api/admin/agent-templates",
        json={
            "name": "Secret Agent",
            "agent_type": "secret_agent",
            "description": "Only for select users",
            "system_prompt": "You are secret.",
            "available_to": [admin_id],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Member should NOT see it
    resp = client.get(
        "/api/agents/available",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    types = {a["agent_type"] for a in resp.get_json()["agents"]}
    assert "secret_agent" not in types

    # Admin SHOULD see it
    resp = client.get(
        "/api/agents/available",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    types = {a["agent_type"] for a in resp.get_json()["agents"]}
    assert "secret_agent" in types


# --- Member self-service tests ---


def test_member_enable_agent(client):
    """Member can enable an available agent for themselves."""
    admin_token, _ = _register_admin(client)
    member_token, _ = _register_member(client, admin_token)

    resp = client.put(
        "/api/agents/my/health_advisor",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["agent_type"] == "health_advisor"
    assert data["enabled"] is True


def test_member_enable_unavailable(client):
    """Member cannot enable an agent that is not available to them."""
    admin_token, admin_id = _register_admin(client)
    member_token, _ = _register_member(client, admin_token)

    # Create a restricted template
    client.post(
        "/api/admin/agent-templates",
        json={
            "name": "VIP Agent",
            "agent_type": "vip_agent",
            "description": "VIP only",
            "system_prompt": "You are VIP.",
            "available_to": [admin_id],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    resp = client.put(
        "/api/agents/my/vip_agent",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403
    assert "not available" in resp.get_json()["error"]


def test_member_disable_agent(client):
    """Member can disable their own agent."""
    admin_token, _ = _register_admin(client)
    member_token, _ = _register_member(client, admin_token)

    # Enable first
    client.put(
        "/api/agents/my/health_advisor",
        headers={"Authorization": f"Bearer {member_token}"},
    )

    # Disable
    resp = client.delete(
        "/api/agents/my/health_advisor",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    # Verify gone
    resp = client.get(
        "/api/agents/my",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert len(resp.get_json()["agent_configs"]) == 0


def test_member_list_my_agents(client):
    """Member can list their own agent configs."""
    admin_token, _ = _register_admin(client)
    member_token, _ = _register_member(client, admin_token)

    # Enable an agent
    client.put(
        "/api/agents/my/health_advisor",
        headers={"Authorization": f"Bearer {member_token}"},
    )

    resp = client.get(
        "/api/agents/my",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 200
    configs = resp.get_json()["agent_configs"]
    assert len(configs) == 1
    assert configs[0]["agent_type"] == "health_advisor"


# --- Backward compatibility: existing agent_config routes still work ---


def test_agent_types_from_templates(client):
    """GET /api/admin/agents/types now reads from templates table."""
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


def test_admin_configure_custom_template_agent(client):
    """Admin can enable a custom template agent for a member via existing routes."""
    admin_token, _ = _register_admin(client)
    _, member_id = _register_member(client, admin_token)

    # Create custom template
    client.post(
        "/api/admin/agent-templates",
        json={
            "name": "Homework Helper",
            "agent_type": "homework_helper",
            "description": "Helps with homework",
            "system_prompt": "You help with homework.",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Use existing agent config route to enable it
    resp = client.put(
        f"/api/admin/agents/{member_id}/homework_helper",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["agent_type"] == "homework_helper"


def test_available_agents_shows_enabled_status(client):
    """The available agents endpoint shows whether each agent is enabled."""
    admin_token, _ = _register_admin(client)
    member_token, _ = _register_member(client, admin_token)

    # Enable health_advisor
    client.put(
        "/api/agents/my/health_advisor",
        headers={"Authorization": f"Bearer {member_token}"},
    )

    resp = client.get(
        "/api/agents/available",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    agents = resp.get_json()["agents"]
    ha = next(a for a in agents if a["agent_type"] == "health_advisor")
    assert ha["enabled"] is True

    la = next(a for a in agents if a["agent_type"] == "logistics_assistant")
    assert la["enabled"] is False
