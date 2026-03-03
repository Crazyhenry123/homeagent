import pytest


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


def test_create_relationship(client):
    admin_token, admin_id = _register_admin(client)
    _, member_id = _register_member(client, admin_token, "Child User")

    resp = client.post(
        "/api/admin/family/relationships",
        json={
            "user_id": admin_id,
            "related_user_id": member_id,
            "relationship_type": "parent_of",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["user_id"] == admin_id
    assert data["related_user_id"] == member_id
    assert data["relationship_type"] == "parent_of"


def test_bidirectional_relationship(client, app):
    admin_token, admin_id = _register_admin(client)
    _, member_id = _register_member(client, admin_token, "Child User")

    # Create parent_of relationship
    client.post(
        "/api/admin/family/relationships",
        json={
            "user_id": admin_id,
            "related_user_id": member_id,
            "relationship_type": "parent_of",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Check forward direction
    resp = client.get(
        f"/api/admin/family/relationships/{admin_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    rels = resp.get_json()["relationships"]
    assert len(rels) == 1
    assert rels[0]["relationship_type"] == "parent_of"

    # Check inverse direction
    resp = client.get(
        f"/api/admin/family/relationships/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    rels = resp.get_json()["relationships"]
    assert len(rels) == 1
    assert rels[0]["relationship_type"] == "child_of"


def test_delete_relationship(client):
    admin_token, admin_id = _register_admin(client)
    _, member_id = _register_member(client, admin_token, "Child User")

    # Create relationship
    client.post(
        "/api/admin/family/relationships",
        json={
            "user_id": admin_id,
            "related_user_id": member_id,
            "relationship_type": "parent_of",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Delete relationship
    resp = client.delete(
        f"/api/admin/family/relationships/{admin_id}/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200

    # Both directions should be gone
    resp = client.get(
        f"/api/admin/family/relationships/{admin_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert len(resp.get_json()["relationships"]) == 0

    resp = client.get(
        f"/api/admin/family/relationships/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert len(resp.get_json()["relationships"]) == 0


def test_invalid_relationship_type(client):
    admin_token, admin_id = _register_admin(client)
    _, member_id = _register_member(client, admin_token)

    resp = client.post(
        "/api/admin/family/relationships",
        json={
            "user_id": admin_id,
            "related_user_id": member_id,
            "relationship_type": "friend_of",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400
    assert "Invalid relationship type" in resp.get_json()["error"]


def test_self_relationship_rejected(client):
    admin_token, admin_id = _register_admin(client)

    resp = client.post(
        "/api/admin/family/relationships",
        json={
            "user_id": admin_id,
            "related_user_id": admin_id,
            "relationship_type": "parent_of",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400
    assert "yourself" in resp.get_json()["error"].lower()


def test_missing_fields(client):
    admin_token, _ = _register_admin(client)

    resp = client.post(
        "/api/admin/family/relationships",
        json={"user_id": "abc"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400


def test_get_all_relationships(client):
    admin_token, admin_id = _register_admin(client)
    _, child_id = _register_member(client, admin_token, "Child")

    client.post(
        "/api/admin/family/relationships",
        json={
            "user_id": admin_id,
            "related_user_id": child_id,
            "relationship_type": "parent_of",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    resp = client.get(
        "/api/admin/family/relationships",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    rels = resp.get_json()["relationships"]
    # Should have both directions
    assert len(rels) == 2


def test_build_family_context(client, app):
    admin_token, admin_id = _register_admin(client)
    _, child_id = _register_member(client, admin_token, "Child User")

    client.post(
        "/api/admin/family/relationships",
        json={
            "user_id": admin_id,
            "related_user_id": child_id,
            "relationship_type": "parent_of",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    from app.services.family_tree import build_family_context

    with app.app_context():
        ctx = build_family_context(admin_id)
        assert "Family relationships:" in ctx
        assert "Child User" in ctx
        assert "child" in ctx.lower()

        # Check inverse
        ctx_child = build_family_context(child_id)
        assert "Family relationships:" in ctx_child
        assert "Admin User" in ctx_child
        assert "parent" in ctx_child.lower()


def test_family_context_in_system_prompt(client, app):
    admin_token, admin_id = _register_admin(client)
    _, child_id = _register_member(client, admin_token, "Child User")

    client.post(
        "/api/admin/family/relationships",
        json={
            "user_id": admin_id,
            "related_user_id": child_id,
            "relationship_type": "parent_of",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    from app.services.agent_orchestrator import _build_system_prompt

    with app.app_context():
        prompt = _build_system_prompt(admin_id, "You are a helpful assistant.")
        assert "Family relationships:" in prompt
        assert "Child User" in prompt


def test_no_family_context_when_no_relationships(client, app):
    admin_token, admin_id = _register_admin(client)

    from app.services.agent_orchestrator import _build_system_prompt

    with app.app_context():
        prompt = _build_system_prompt(admin_id, "You are a helpful assistant.")
        assert "Family relationships:" not in prompt


def test_cascade_delete_removes_relationships(client, app):
    admin_token, admin_id = _register_admin(client)
    _, member_id = _register_member(client, admin_token, "Child User")

    # Create relationship
    client.post(
        "/api/admin/family/relationships",
        json={
            "user_id": admin_id,
            "related_user_id": member_id,
            "relationship_type": "parent_of",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Delete the member
    client.delete(
        f"/api/admin/profiles/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Admin should no longer have the relationship
    resp = client.get(
        f"/api/admin/family/relationships/{admin_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert len(resp.get_json()["relationships"]) == 0


def test_spouse_relationship_symmetric(client, app):
    admin_token, admin_id = _register_admin(client)
    _, spouse_id = _register_member(client, admin_token, "Spouse User")

    client.post(
        "/api/admin/family/relationships",
        json={
            "user_id": admin_id,
            "related_user_id": spouse_id,
            "relationship_type": "spouse_of",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Both sides should see spouse_of
    resp = client.get(
        f"/api/admin/family/relationships/{admin_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    rels = resp.get_json()["relationships"]
    assert len(rels) == 1
    assert rels[0]["relationship_type"] == "spouse_of"

    resp = client.get(
        f"/api/admin/family/relationships/{spouse_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    rels = resp.get_json()["relationships"]
    assert len(rels) == 1
    assert rels[0]["relationship_type"] == "spouse_of"


def test_member_cannot_access_family_routes(client):
    admin_token, admin_id = _register_admin(client)
    member_token, _ = _register_member(client, admin_token)

    resp = client.get(
        "/api/admin/family/relationships",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403
