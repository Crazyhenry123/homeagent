"""Tests for member permissions and default agent auto-enablement."""


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


# --- Default Agents Auto-Enabled on Registration ---


class TestDefaultAgentsOnRegistration:
    def test_default_agents_auto_enabled(self, client):
        """New members should have default agents auto-enabled."""
        admin_token, _ = _register_admin(client)
        member_token, member_id = _register_member(client, admin_token)

        resp = client.get(
            "/api/agents/my",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert resp.status_code == 200
        configs = resp.get_json()["agent_configs"]
        agent_types = {c["agent_type"] for c in configs}

        assert "health_advisor" in agent_types
        assert "logistics_assistant" in agent_types

    def test_default_agents_are_enabled_true(self, client):
        """Auto-enabled agents should have enabled=True."""
        admin_token, _ = _register_admin(client)
        member_token, _ = _register_member(client, admin_token)

        resp = client.get(
            "/api/agents/my",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        configs = resp.get_json()["agent_configs"]
        for config in configs:
            assert config["enabled"] is True

    def test_non_default_agents_not_auto_enabled(self, client):
        """Shopping assistant (is_default=False) should not be auto-enabled."""
        admin_token, _ = _register_admin(client)
        member_token, _ = _register_member(client, admin_token)

        resp = client.get(
            "/api/agents/my",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        configs = resp.get_json()["agent_configs"]
        agent_types = {c["agent_type"] for c in configs}

        assert "shopping_assistant" not in agent_types


# --- Permission CRUD ---


class TestPermissionCRUD:
    def test_grant_permission(self, client):
        admin_token, _ = _register_admin(client)
        member_token, _ = _register_member(client, admin_token)

        resp = client.put(
            "/api/permissions/email_access",
            json={"config": {"email_address": "test@example.com", "provider": "gmail"}},
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["permission_type"] == "email_access"
        assert data["status"] == "active"
        assert data["config"]["email_address"] == "test@example.com"

    def test_get_permissions(self, client):
        admin_token, _ = _register_admin(client)
        member_token, _ = _register_member(client, admin_token)

        # Grant two permissions
        client.put(
            "/api/permissions/email_access",
            json={"config": {"email_address": "test@example.com", "provider": "gmail"}},
            headers={"Authorization": f"Bearer {member_token}"},
        )
        client.put(
            "/api/permissions/health_data",
            json={"config": {"consent_given": True, "data_sources": ["healthkit"]}},
            headers={"Authorization": f"Bearer {member_token}"},
        )

        resp = client.get(
            "/api/permissions",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert resp.status_code == 200
        permissions = resp.get_json()["permissions"]
        assert len(permissions) == 2
        types = {p["permission_type"] for p in permissions}
        assert types == {"email_access", "health_data"}

    def test_revoke_permission(self, client):
        admin_token, _ = _register_admin(client)
        member_token, _ = _register_member(client, admin_token)

        # Grant then revoke
        client.put(
            "/api/permissions/email_access",
            json={"config": {"email_address": "test@example.com", "provider": "gmail"}},
            headers={"Authorization": f"Bearer {member_token}"},
        )
        resp = client.delete(
            "/api/permissions/email_access",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        # Verify it's no longer in active permissions
        resp = client.get(
            "/api/permissions",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        permissions = resp.get_json()["permissions"]
        assert len(permissions) == 0

    def test_revoke_nonexistent_permission(self, client):
        admin_token, _ = _register_admin(client)
        member_token, _ = _register_member(client, admin_token)

        resp = client.delete(
            "/api/permissions/email_access",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert resp.status_code == 404

    def test_invalid_permission_type(self, client):
        admin_token, _ = _register_admin(client)
        member_token, _ = _register_member(client, admin_token)

        resp = client.put(
            "/api/permissions/invalid_type",
            json={"config": {}},
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert resp.status_code == 400
        assert "Invalid permission type" in resp.get_json()["error"]

    def test_grant_updates_existing(self, client):
        """Granting the same permission again should update it."""
        admin_token, _ = _register_admin(client)
        member_token, _ = _register_member(client, admin_token)

        client.put(
            "/api/permissions/email_access",
            json={"config": {"email_address": "old@example.com", "provider": "gmail"}},
            headers={"Authorization": f"Bearer {member_token}"},
        )
        client.put(
            "/api/permissions/email_access",
            json={"config": {"email_address": "new@example.com", "provider": "outlook"}},
            headers={"Authorization": f"Bearer {member_token}"},
        )

        resp = client.get(
            "/api/permissions",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        permissions = resp.get_json()["permissions"]
        assert len(permissions) == 1
        assert permissions[0]["config"]["email_address"] == "new@example.com"
        assert permissions[0]["config"]["provider"] == "outlook"


# --- Permission Requirements for Agents ---


class TestPermissionRequirements:
    def test_get_required_permissions_health_advisor(self, client):
        admin_token, _ = _register_admin(client)
        member_token, _ = _register_member(client, admin_token)

        resp = client.get(
            "/api/permissions/required/health_advisor",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["agent_type"] == "health_advisor"
        assert set(data["required_permissions"]) == {"health_data", "medical_records"}

    def test_get_required_permissions_logistics(self, client):
        admin_token, _ = _register_admin(client)
        member_token, _ = _register_member(client, admin_token)

        resp = client.get(
            "/api/permissions/required/logistics_assistant",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["agent_type"] == "logistics_assistant"
        assert set(data["required_permissions"]) == {"email_access", "calendar_access"}

    def test_get_required_permissions_unknown_agent(self, client):
        admin_token, _ = _register_admin(client)
        member_token, _ = _register_member(client, admin_token)

        resp = client.get(
            "/api/permissions/required/nonexistent_agent",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert resp.status_code == 404

    def test_available_agents_include_required_permissions(self, client):
        """Available agents response should include required_permissions field."""
        admin_token, _ = _register_admin(client)
        member_token, _ = _register_member(client, admin_token)

        resp = client.get(
            "/api/agents/available",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert resp.status_code == 200
        agents = resp.get_json()["agents"]

        health = next(a for a in agents if a["agent_type"] == "health_advisor")
        assert set(health["required_permissions"]) == {"health_data", "medical_records"}
        assert health["is_default"] is True

        logistics = next(a for a in agents if a["agent_type"] == "logistics_assistant")
        assert set(logistics["required_permissions"]) == {"email_access", "calendar_access"}
        assert logistics["is_default"] is True

    def test_agent_types_include_required_permissions(self, client):
        """Admin agent types response should include required_permissions."""
        admin_token, _ = _register_admin(client)

        resp = client.get(
            "/api/admin/agents/types",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        agent_types = resp.get_json()["agent_types"]

        assert "required_permissions" in agent_types["health_advisor"]
        assert agent_types["health_advisor"]["is_default"] is True


# --- Auth Required ---


class TestPermissionAuth:
    def test_permissions_require_auth(self, client):
        resp = client.get("/api/permissions")
        assert resp.status_code == 401

    def test_grant_requires_auth(self, client):
        resp = client.put(
            "/api/permissions/email_access",
            json={"config": {}},
        )
        assert resp.status_code == 401

    def test_revoke_requires_auth(self, client):
        resp = client.delete("/api/permissions/email_access")
        assert resp.status_code == 401
