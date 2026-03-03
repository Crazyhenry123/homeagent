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


def test_get_own_profile(client):
    token, user_id = _register_admin(client)
    resp = client.get(
        "/api/profiles/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["user_id"] == user_id
    assert data["display_name"] == "Admin User"
    assert data["role"] == "admin"


def test_update_own_profile(client):
    token, _ = _register_admin(client)
    resp = client.put(
        "/api/profiles/me",
        json={
            "family_role": "Parent",
            "interests": ["cooking", "hiking"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["family_role"] == "Parent"
    assert data["interests"] == ["cooking", "hiking"]


def test_update_profile_ignores_unknown_fields(client):
    token, _ = _register_admin(client)
    resp = client.put(
        "/api/profiles/me",
        json={"unknown_field": "value", "display_name": "New Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["display_name"] == "New Name"
    assert "unknown_field" not in data


def test_profile_requires_auth(client):
    resp = client.get("/api/profiles/me")
    assert resp.status_code == 401


def test_admin_get_member_profile(client):
    admin_token, _ = _register_admin(client)
    member_token, member_id = _register_member(client, admin_token)

    resp = client.get(
        f"/api/admin/profiles/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["display_name"] == "Member User"


def test_admin_update_member_profile(client):
    admin_token, _ = _register_admin(client)
    _, member_id = _register_member(client, admin_token)

    resp = client.put(
        f"/api/admin/profiles/{member_id}",
        json={"health_notes": "Allergic to peanuts"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["health_notes"] == "Allergic to peanuts"


def test_member_cannot_access_admin_profiles(client):
    admin_token, admin_id = _register_admin(client)
    member_token, _ = _register_member(client, admin_token)

    resp = client.get(
        f"/api/admin/profiles/{admin_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403


def test_admin_list_profiles(client):
    admin_token, _ = _register_admin(client)
    _register_member(client, admin_token)

    resp = client.get(
        "/api/admin/profiles",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["profiles"]) == 2


def test_get_nonexistent_profile(client):
    admin_token, _ = _register_admin(client)
    resp = client.get(
        "/api/admin/profiles/nonexistent",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


def test_registration_creates_profile(client):
    """Verify that registering a user automatically creates a profile."""
    token, user_id = _register_admin(client)
    resp = client.get(
        "/api/profiles/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["user_id"] == user_id
    assert data["created_at"] is not None
