"""Tests for the family invite system."""


def _register_admin(client):
    """Register an admin user and return (user_id, token)."""
    resp = client.post(
        "/api/auth/register",
        json={
            "invite_code": "FAMILY",
            "device_name": "Admin Phone",
            "platform": "ios",
            "display_name": "Admin Owner",
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    return data["user_id"], data["device_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_create_family(client):
    """Admin auto-creates a family on registration and can retrieve it."""
    user_id, token = _register_admin(client)

    # Family is auto-created on admin registration, so GET should work
    resp = client.get(
        "/api/family",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["family"]["owner_user_id"] == user_id
    assert "family_id" in data["family"]


def test_auto_create_family_on_admin_registration(client):
    """Admin registration auto-creates a family."""
    user_id, token = _register_admin(client)

    # The admin should already be in a family (auto-created)
    resp = client.get(
        "/api/family",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["family"]["owner_user_id"] == user_id
    assert len(data["members"]) == 1
    assert data["members"][0]["user_id"] == user_id
    assert data["members"][0]["role"] == "owner"


def test_cannot_create_duplicate_family(client):
    """Admin cannot create a second family."""
    _, token = _register_admin(client)

    resp = client.post(
        "/api/family",
        json={"name": "Second Family"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 409


def test_invite_member_by_email(client):
    """Owner can invite a member by email."""
    _, token = _register_admin(client)

    resp = client.post(
        "/api/family/invite",
        json={"email": "member@example.com"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["invited_email"] == "member@example.com"
    assert "code" in data
    assert len(data["code"]) == 6
    assert data["family_name"] is not None
    # SES is not enabled in tests
    assert data["email_sent"] is False


def test_register_with_invite_joins_family(client):
    """Member registering with a family invite code joins the family."""
    admin_id, admin_token = _register_admin(client)

    # Invite a member
    invite_resp = client.post(
        "/api/family/invite",
        json={"email": "member@example.com"},
        headers=_auth_headers(admin_token),
    )
    invite_code = invite_resp.get_json()["code"]

    # Register as the invited member
    reg_resp = client.post(
        "/api/auth/register",
        json={
            "invite_code": invite_code,
            "device_name": "Member Phone",
            "platform": "android",
            "display_name": "Family Member",
        },
    )
    assert reg_resp.status_code == 201
    member_id = reg_resp.get_json()["user_id"]

    # Check the family now has 2 members
    family_resp = client.get(
        "/api/family",
        headers=_auth_headers(admin_token),
    )
    assert family_resp.status_code == 200
    data = family_resp.get_json()
    member_ids = [m["user_id"] for m in data["members"]]
    assert admin_id in member_ids
    assert member_id in member_ids
    assert len(data["members"]) == 2


def test_list_family_members(client):
    """Can list family members."""
    _, token = _register_admin(client)

    resp = client.get(
        "/api/family",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "members" in data
    assert len(data["members"]) >= 1


def test_cancel_invite(client):
    """Owner can cancel a pending invite."""
    _, token = _register_admin(client)

    # Create invite
    invite_resp = client.post(
        "/api/family/invite",
        json={"email": "cancel@example.com"},
        headers=_auth_headers(token),
    )
    code = invite_resp.get_json()["code"]

    # Cancel it
    cancel_resp = client.delete(
        f"/api/family/invites/{code}",
        headers=_auth_headers(token),
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.get_json()["status"] == "cancelled"

    # Verify it's no longer in pending invites
    invites_resp = client.get(
        "/api/family/invites",
        headers=_auth_headers(token),
    )
    pending_codes = [i["code"] for i in invites_resp.get_json()["invites"]]
    assert code not in pending_codes


def test_cancelled_invite_cannot_be_used(client):
    """A cancelled invite code cannot be used to register."""
    _, token = _register_admin(client)

    # Create and cancel invite
    invite_resp = client.post(
        "/api/family/invite",
        json={"email": "cancelled@example.com"},
        headers=_auth_headers(token),
    )
    code = invite_resp.get_json()["code"]
    client.delete(
        f"/api/family/invites/{code}",
        headers=_auth_headers(token),
    )

    # Try to register with cancelled code
    reg_resp = client.post(
        "/api/auth/register",
        json={
            "invite_code": code,
            "device_name": "Phone",
            "platform": "ios",
            "display_name": "Bad User",
        },
    )
    assert reg_resp.status_code == 400


def test_only_owner_can_invite(client):
    """Non-admin users cannot create invites."""
    _, admin_token = _register_admin(client)

    # Create a regular invite code
    code_resp = client.post(
        "/api/admin/invite-codes",
        headers=_auth_headers(admin_token),
    )
    member_code = code_resp.get_json()["code"]

    # Register a regular member
    reg_resp = client.post(
        "/api/auth/register",
        json={
            "invite_code": member_code,
            "device_name": "Member Phone",
            "platform": "ios",
            "display_name": "Regular Member",
        },
    )
    member_token = reg_resp.get_json()["device_token"]

    # Try to invite as a regular member — should fail (403)
    invite_resp = client.post(
        "/api/family/invite",
        json={"email": "another@example.com"},
        headers=_auth_headers(member_token),
    )
    assert invite_resp.status_code == 403


def test_list_pending_invites(client):
    """Owner can list pending invites."""
    _, token = _register_admin(client)

    # Create two invites
    client.post(
        "/api/family/invite",
        json={"email": "a@example.com"},
        headers=_auth_headers(token),
    )
    client.post(
        "/api/family/invite",
        json={"email": "b@example.com"},
        headers=_auth_headers(token),
    )

    resp = client.get(
        "/api/family/invites",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200
    invites = resp.get_json()["invites"]
    assert len(invites) >= 2
    emails = [i.get("invited_email") for i in invites]
    assert "a@example.com" in emails
    assert "b@example.com" in emails


def test_get_family_no_family(client):
    """User not in a family gets 404."""
    # Register admin — auto-creates family, so we need a non-admin user
    _, admin_token = _register_admin(client)

    # Create a regular invite code
    code_resp = client.post(
        "/api/admin/invite-codes",
        headers=_auth_headers(admin_token),
    )
    member_code = code_resp.get_json()["code"]

    # Register a member (without family_id on the invite code)
    reg_resp = client.post(
        "/api/auth/register",
        json={
            "invite_code": member_code,
            "device_name": "Phone",
            "platform": "ios",
            "display_name": "Lonely Member",
        },
    )
    member_token = reg_resp.get_json()["device_token"]

    # This member is not in a family
    resp = client.get(
        "/api/family",
        headers=_auth_headers(member_token),
    )
    assert resp.status_code == 404
