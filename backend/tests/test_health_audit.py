"""Tests for health record audit trail — create/update/delete produce entries, admin-only."""


def _register_admin(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "invite_code": "FAMILY",
            "device_name": "Admin Phone",
            "platform": "ios",
            "display_name": "Admin",
        },
    )
    data = resp.get_json()
    return data["user_id"], data["device_token"]


def _register_member(client, admin_token, name="Member"):
    resp = client.post(
        "/api/admin/invite-codes",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    code = resp.get_json()["code"]
    resp = client.post(
        "/api/auth/register",
        json={
            "invite_code": code,
            "device_name": "Phone",
            "platform": "android",
            "display_name": name,
        },
    )
    data = resp.get_json()
    return data["user_id"], data["device_token"]


def test_create_produces_audit_entry(client):
    admin_id, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    resp = client.post(
        f"/api/admin/health-records/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"record_type": "condition", "data": {"name": "Asthma"}},
    )
    assert resp.status_code == 201
    record_id = resp.get_json()["record_id"]

    audit_resp = client.get(
        f"/api/admin/health-records/{member_id}/{record_id}/audit",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert audit_resp.status_code == 200
    entries = audit_resp.get_json()["audit_log"]
    assert len(entries) == 1
    assert entries[0]["action"] == "create"
    assert entries[0]["actor_id"] == admin_id
    assert entries[0]["user_id"] == member_id
    assert "record_snapshot" in entries[0]


def test_update_produces_audit_entry(client):
    admin_id, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    resp = client.post(
        f"/api/admin/health-records/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "record_type": "condition",
            "data": {"name": "Asthma", "severity": "mild"},
        },
    )
    record_id = resp.get_json()["record_id"]

    client.put(
        f"/api/admin/health-records/{member_id}/{record_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"data": {"name": "Asthma", "severity": "moderate"}},
    )

    audit_resp = client.get(
        f"/api/admin/health-records/{member_id}/{record_id}/audit",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    entries = audit_resp.get_json()["audit_log"]
    assert len(entries) == 2  # create + update
    # Newest first
    assert entries[0]["action"] == "update"
    assert "changes" in entries[0]
    assert entries[0]["changes"]["before"]["data"]["severity"] == "mild"
    assert entries[0]["changes"]["after"]["data"]["severity"] == "moderate"


def test_delete_produces_audit_entry(client):
    admin_id, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    resp = client.post(
        f"/api/admin/health-records/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"record_type": "allergy", "data": {"name": "Peanuts"}},
    )
    record_id = resp.get_json()["record_id"]

    client.delete(
        f"/api/admin/health-records/{member_id}/{record_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    audit_resp = client.get(
        f"/api/admin/health-records/{member_id}/{record_id}/audit",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    entries = audit_resp.get_json()["audit_log"]
    assert len(entries) == 2  # create + delete
    assert entries[0]["action"] == "delete"
    assert entries[0]["record_snapshot"]["data"]["name"] == "Peanuts"


def test_user_audit_log(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    # Create two records
    for name in ["Asthma", "Eczema"]:
        client.post(
            f"/api/admin/health-records/{member_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"record_type": "condition", "data": {"name": name}},
        )

    audit_resp = client.get(
        f"/api/admin/health-records/{member_id}/audit-log",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert audit_resp.status_code == 200
    entries = audit_resp.get_json()["audit_log"]
    assert len(entries) == 2
    assert all(e["action"] == "create" for e in entries)


def test_audit_log_empty(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    audit_resp = client.get(
        f"/api/admin/health-records/{member_id}/audit-log",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert audit_resp.status_code == 200
    assert audit_resp.get_json()["audit_log"] == []


def test_audit_log_requires_admin(client):
    _, admin_token = _register_admin(client)
    member_id, member_token = _register_member(client, admin_token)

    resp = client.get(
        f"/api/admin/health-records/{member_id}/audit-log",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403
