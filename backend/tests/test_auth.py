def test_register_with_valid_invite_code(client):
    response = client.post(
        "/api/auth/register",
        json={
            "invite_code": "FAMILY",
            "device_name": "Test iPhone",
            "platform": "ios",
            "display_name": "Test User",
        },
    )
    assert response.status_code == 201
    data = response.get_json()
    assert "user_id" in data
    assert "device_token" in data


def test_register_with_invalid_invite_code(client):
    response = client.post(
        "/api/auth/register",
        json={
            "invite_code": "BADCODE",
            "device_name": "Test iPhone",
            "platform": "ios",
            "display_name": "Test User",
        },
    )
    assert response.status_code == 400
    assert "Invalid invite code" in response.get_json()["error"]


def test_register_missing_fields(client):
    response = client.post(
        "/api/auth/register",
        json={"invite_code": "FAMILY"},
    )
    assert response.status_code == 400
    assert "Missing fields" in response.get_json()["error"]


def test_register_invalid_platform(client):
    response = client.post(
        "/api/auth/register",
        json={
            "invite_code": "FAMILY",
            "device_name": "Test",
            "platform": "windows",
            "display_name": "Test User",
        },
    )
    assert response.status_code == 400


def test_verify_valid_token(client):
    # Register first
    reg = client.post(
        "/api/auth/register",
        json={
            "invite_code": "FAMILY",
            "device_name": "Test iPhone",
            "platform": "ios",
            "display_name": "Test User",
        },
    )
    token = reg.get_json()["device_token"]

    # Verify
    response = client.post(
        "/api/auth/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["valid"] is True
    assert data["name"] == "Test User"


def test_verify_invalid_token(client):
    response = client.post(
        "/api/auth/verify",
        headers={"Authorization": "Bearer invalidtoken"},
    )
    assert response.status_code == 401


def test_verify_missing_header(client):
    response = client.post("/api/auth/verify")
    assert response.status_code == 401


def test_invite_code_used_only_once(client):
    # First registration succeeds
    response = client.post(
        "/api/auth/register",
        json={
            "invite_code": "FAMILY",
            "device_name": "Device 1",
            "platform": "ios",
            "display_name": "User 1",
        },
    )
    assert response.status_code == 201

    # Second registration with same code fails
    response = client.post(
        "/api/auth/register",
        json={
            "invite_code": "FAMILY",
            "device_name": "Device 2",
            "platform": "android",
            "display_name": "User 2",
        },
    )
    assert response.status_code == 400


def test_admin_can_create_invite_codes(client):
    # Register as admin (FAMILY code is_admin=True)
    reg = client.post(
        "/api/auth/register",
        json={
            "invite_code": "FAMILY",
            "device_name": "Admin Phone",
            "platform": "ios",
            "display_name": "Admin",
        },
    )
    token = reg.get_json()["device_token"]

    # Create invite code
    response = client.post(
        "/api/admin/invite-codes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.get_json()
    assert "code" in data
    assert len(data["code"]) == 6
