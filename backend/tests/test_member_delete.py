def _register_admin(client):
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


def _register_member(client, admin_token, name="Member User"):
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
            "display_name": name,
        },
    )
    data = resp.get_json()
    return data["device_token"], data["user_id"]


def test_admin_deletes_member(client):
    admin_token, _ = _register_admin(client)
    _, member_id = _register_member(client, admin_token)

    resp = client.delete(
        f"/api/admin/profiles/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    # Verify profile is gone
    resp = client.get(
        f"/api/admin/profiles/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


def test_cannot_delete_self(client):
    admin_token, admin_id = _register_admin(client)

    resp = client.delete(
        f"/api/admin/profiles/{admin_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400
    assert "Cannot delete yourself" in resp.get_json()["error"]


def test_cannot_delete_admin(client):
    admin_token, admin_id = _register_admin(client)

    # Create a second admin to try deleting the first
    # (Use a second admin invite code — but we only have FAMILY)
    # Instead, register a member and try to delete admin from that admin's perspective
    # Actually, let's just verify that delete_member rejects admin role
    _, member_id = _register_member(client, admin_token)

    # The registered admin cannot be deleted (role check)
    # We need a second admin — but the test proves the check works:
    # admin_id user has role=admin, so delete should fail
    # We create a roundabout: register member, try from admin to delete admin
    # But admin_id == g.user_id check fires first.
    # Let's instead test via the service directly
    from app.services.user import delete_member
    import pytest

    with client.application.app_context():
        with pytest.raises(ValueError, match="Cannot delete an admin"):
            delete_member(admin_id)


def test_delete_nonexistent_user(client):
    admin_token, _ = _register_admin(client)

    resp = client.delete(
        "/api/admin/profiles/nonexistent",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.get_json()["error"].lower()


def test_member_cannot_delete(client):
    admin_token, admin_id = _register_admin(client)
    member_token, _ = _register_member(client, admin_token)

    resp = client.delete(
        f"/api/admin/profiles/{admin_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403


def test_cascade_deletes_conversations(client, app):
    admin_token, _ = _register_admin(client)
    member_token, member_id = _register_member(client, admin_token)

    # Create a conversation for the member
    from app.services.conversation import create_conversation, add_message

    with app.app_context():
        conv = create_conversation(member_id, "Test Chat")
        add_message(conv["conversation_id"], "user", "Hello")
        add_message(conv["conversation_id"], "assistant", "Hi there")
        conv_id = conv["conversation_id"]

    # Delete the member
    resp = client.delete(
        f"/api/admin/profiles/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200

    # Verify conversation and messages are gone
    from app.services.conversation import get_conversation, get_messages

    with app.app_context():
        assert get_conversation(conv_id) is None
        result = get_messages(conv_id)
        assert len(result["messages"]) == 0


def test_cascade_deletes_devices(client, app):
    admin_token, _ = _register_admin(client)
    member_token, member_id = _register_member(client, admin_token)

    # Delete the member
    resp = client.delete(
        f"/api/admin/profiles/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200

    # The member's token should no longer work
    resp = client.post(
        "/api/auth/verify",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 401
