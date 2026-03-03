"""Tests for health records API — CRUD, filtering, summary, auth, cascade delete."""


def _register_admin(client):
    """Register as admin and return (user_id, token)."""
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
    """Create an invite code and register a member. Returns (user_id, token)."""
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


# ── Admin CRUD ──────────────────────────────────────────────────────


def test_create_health_record(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    resp = client.post(
        f"/api/admin/health-records/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "record_type": "condition",
            "data": {"name": "Asthma", "severity": "mild"},
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["record_type"] == "condition"
    assert data["data"]["name"] == "Asthma"
    assert "record_id" in data


def test_create_health_record_invalid_type(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    resp = client.post(
        f"/api/admin/health-records/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "record_type": "invalid_type",
            "data": {"name": "Test"},
        },
    )
    assert resp.status_code == 400
    assert "Invalid record_type" in resp.get_json()["error"]


def test_create_health_record_missing_fields(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    resp = client.post(
        f"/api/admin/health-records/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"record_type": "condition"},
    )
    assert resp.status_code == 400
    assert "required" in resp.get_json()["error"]


def test_get_health_record(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    # Create
    create_resp = client.post(
        f"/api/admin/health-records/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "record_type": "medication",
            "data": {"name": "Ibuprofen", "dosage": "200mg"},
        },
    )
    record_id = create_resp.get_json()["record_id"]

    # Get
    resp = client.get(
        f"/api/admin/health-records/{member_id}/{record_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["name"] == "Ibuprofen"


def test_get_health_record_not_found(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    resp = client.get(
        f"/api/admin/health-records/{member_id}/nonexistent",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


def test_list_health_records(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    # Create two records
    for rt, name in [("condition", "Asthma"), ("medication", "Inhaler")]:
        client.post(
            f"/api/admin/health-records/{member_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"record_type": rt, "data": {"name": name}},
        )

    resp = client.get(
        f"/api/admin/health-records/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.get_json()["records"]) == 2


def test_list_health_records_filter_by_type(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    for rt in ["condition", "medication", "condition"]:
        client.post(
            f"/api/admin/health-records/{member_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"record_type": rt, "data": {"name": f"Test {rt}"}},
        )

    resp = client.get(
        f"/api/admin/health-records/{member_id}?record_type=condition",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    records = resp.get_json()["records"]
    assert len(records) == 2
    assert all(r["record_type"] == "condition" for r in records)


def test_update_health_record(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    create_resp = client.post(
        f"/api/admin/health-records/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "record_type": "condition",
            "data": {"name": "Asthma", "severity": "mild"},
        },
    )
    record_id = create_resp.get_json()["record_id"]

    resp = client.put(
        f"/api/admin/health-records/{member_id}/{record_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"data": {"name": "Asthma", "severity": "moderate"}},
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["severity"] == "moderate"


def test_update_health_record_not_found(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    resp = client.put(
        f"/api/admin/health-records/{member_id}/nonexistent",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"data": {"name": "Test"}},
    )
    assert resp.status_code == 404


def test_delete_health_record(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    create_resp = client.post(
        f"/api/admin/health-records/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"record_type": "allergy", "data": {"name": "Peanuts"}},
    )
    record_id = create_resp.get_json()["record_id"]

    resp = client.delete(
        f"/api/admin/health-records/{member_id}/{record_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    # Verify deleted
    resp = client.get(
        f"/api/admin/health-records/{member_id}/{record_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


def test_delete_health_record_not_found(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    resp = client.delete(
        f"/api/admin/health-records/{member_id}/nonexistent",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


def test_health_summary(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    for rt, name in [
        ("condition", "Asthma"),
        ("medication", "Inhaler"),
        ("allergy", "Peanuts"),
    ]:
        client.post(
            f"/api/admin/health-records/{member_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"record_type": rt, "data": {"name": name}},
        )

    resp = client.get(
        f"/api/admin/health-records/{member_id}/summary",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["record_count"] == 3
    assert "condition" in data["by_type"]
    assert "medication" in data["by_type"]
    assert "allergy" in data["by_type"]


# ── Self-access routes ──────────────────────────────────────────────


def test_self_access_health_records(client):
    _, admin_token = _register_admin(client)
    member_id, member_token = _register_member(client, admin_token)

    # Admin creates a record for the member
    client.post(
        f"/api/admin/health-records/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"record_type": "condition", "data": {"name": "Eczema"}},
    )

    # Member accesses own records
    resp = client.get(
        "/api/health-records/me",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.get_json()["records"]) == 1


def test_self_access_health_summary(client):
    _, admin_token = _register_admin(client)
    member_id, member_token = _register_member(client, admin_token)

    client.post(
        f"/api/admin/health-records/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"record_type": "vital", "data": {"bp": "120/80"}},
    )

    resp = client.get(
        "/api/health-records/me/summary",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["record_count"] == 1


# ── Auth checks ─────────────────────────────────────────────────────


def test_admin_routes_require_admin(client):
    _, admin_token = _register_admin(client)
    _, member_token = _register_member(client, admin_token)

    resp = client.get(
        "/api/admin/health-records/some_user",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert resp.status_code == 403


def test_self_access_requires_auth(client):
    resp = client.get("/api/health-records/me")
    assert resp.status_code == 401


# ── Cascade delete ──────────────────────────────────────────────────


def test_cascade_delete_removes_health_records(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    # Create records
    client.post(
        f"/api/admin/health-records/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"record_type": "condition", "data": {"name": "Test"}},
    )

    # Delete member
    client.delete(
        f"/api/admin/profiles/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Records should be gone
    resp = client.get(
        f"/api/admin/health-records/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.get_json()["records"]) == 0


# ── Health reports ──────────────────────────────────────────────────


def test_generate_health_report(client):
    _, admin_token = _register_admin(client)
    member_id, _ = _register_member(client, admin_token)

    client.post(
        f"/api/admin/health-records/{member_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"record_type": "condition", "data": {"name": "Asthma"}},
    )

    resp = client.post(
        f"/api/admin/health-reports/{member_id}/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["user_id"] == member_id
    assert data["records_summary"]["record_count"] == 1


def test_generate_health_report_user_not_found(client):
    _, admin_token = _register_admin(client)

    resp = client.post(
        "/api/admin/health-reports/nonexistent/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404
