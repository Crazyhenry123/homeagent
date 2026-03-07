from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError


def _cognito_client_error(code: str, message: str) -> ClientError:
    """Create a botocore ClientError with the given code and message."""
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        "operation_name",
    )


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------


@patch("app.services.cognito.boto3")
def test_signup_success(mock_boto3, client):
    """Test successful owner signup via Cognito."""
    mock_cognito = MagicMock()
    mock_boto3.client.return_value = mock_cognito
    mock_cognito.sign_up.return_value = {"UserSub": "cognito-sub-123"}

    response = client.post(
        "/api/auth/signup",
        json={
            "email": "owner@example.com",
            "password": "Test1234!",
            "display_name": "Test Owner",
        },
    )
    assert response.status_code == 201
    data = response.get_json()
    assert "user_id" in data
    assert data["email"] == "owner@example.com"


@patch("app.services.cognito.boto3")
def test_signup_duplicate_email(mock_boto3, client):
    """Test signup with an email that already exists in Cognito."""
    mock_cognito = MagicMock()
    mock_boto3.client.return_value = mock_cognito
    mock_cognito.sign_up.side_effect = _cognito_client_error(
        "UsernameExistsException", "An account with the given email already exists."
    )

    response = client.post(
        "/api/auth/signup",
        json={
            "email": "existing@example.com",
            "password": "Test1234!",
            "display_name": "Existing User",
        },
    )
    assert response.status_code == 409
    data = response.get_json()
    assert "already exists" in data["error"]


def test_signup_missing_fields(client):
    """Test signup with missing required fields."""
    response = client.post(
        "/api/auth/signup",
        json={"email": "test@example.com"},
    )
    assert response.status_code == 400
    assert "Missing fields" in response.get_json()["error"]


def test_signup_invalid_email(client):
    """Test signup with invalid email format."""
    response = client.post(
        "/api/auth/signup",
        json={
            "email": "not-an-email",
            "password": "Test1234!",
            "display_name": "Test",
        },
    )
    assert response.status_code == 400
    assert "Invalid email" in response.get_json()["error"]


def test_signup_weak_password(client):
    """Test signup with a password that doesn't meet requirements."""
    response = client.post(
        "/api/auth/signup",
        json={
            "email": "test@example.com",
            "password": "short",
            "display_name": "Test",
        },
    )
    assert response.status_code == 400
    assert "Password" in response.get_json()["error"]


def test_signup_password_no_special_char(client):
    """Test signup with a password missing special character."""
    response = client.post(
        "/api/auth/signup",
        json={
            "email": "test@example.com",
            "password": "Test1234a",
            "display_name": "Test",
        },
    )
    assert response.status_code == 400
    assert "special character" in response.get_json()["error"]


# ---------------------------------------------------------------------------
# Confirm
# ---------------------------------------------------------------------------


@patch("app.services.cognito.boto3")
def test_confirm_success(mock_boto3, client):
    """Test successful email confirmation."""
    mock_cognito = MagicMock()
    mock_boto3.client.return_value = mock_cognito
    mock_cognito.confirm_sign_up.return_value = {}

    response = client.post(
        "/api/auth/confirm",
        json={
            "email": "owner@example.com",
            "confirmation_code": "123456",
        },
    )
    assert response.status_code == 200
    assert response.get_json()["confirmed"] is True


@patch("app.services.cognito.boto3")
def test_confirm_invalid_code(mock_boto3, client):
    """Test confirmation with wrong code."""
    mock_cognito = MagicMock()
    mock_boto3.client.return_value = mock_cognito
    mock_cognito.confirm_sign_up.side_effect = _cognito_client_error(
        "CodeMismatchException", "Invalid verification code provided."
    )

    response = client.post(
        "/api/auth/confirm",
        json={
            "email": "owner@example.com",
            "confirmation_code": "000000",
        },
    )
    assert response.status_code == 400
    assert "Invalid verification code" in response.get_json()["error"]


def test_confirm_missing_fields(client):
    """Test confirmation with missing fields."""
    response = client.post(
        "/api/auth/confirm",
        json={"email": "test@example.com"},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@patch("app.services.cognito.boto3")
def test_login_success(mock_boto3, client):
    """Test successful login returns tokens and user info."""
    mock_cognito = MagicMock()
    mock_boto3.client.return_value = mock_cognito

    # First, sign up the user to create the DynamoDB record
    mock_cognito.sign_up.return_value = {"UserSub": "cognito-sub-456"}
    signup_resp = client.post(
        "/api/auth/signup",
        json={
            "email": "login@example.com",
            "password": "Test1234!",
            "display_name": "Login User",
        },
    )
    assert signup_resp.status_code == 201

    # Now mock the login
    mock_cognito.initiate_auth.return_value = {
        "AuthenticationResult": {
            "IdToken": "id-token-abc",
            "AccessToken": "access-token-abc",
            "RefreshToken": "refresh-token-abc",
        }
    }

    response = client.post(
        "/api/auth/login",
        json={
            "email": "login@example.com",
            "password": "Test1234!",
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert "tokens" in data
    assert data["tokens"]["id_token"] == "id-token-abc"
    assert data["tokens"]["access_token"] == "access-token-abc"
    assert data["tokens"]["refresh_token"] == "refresh-token-abc"
    assert "user" in data
    assert data["user"]["name"] == "Login User"
    assert data["user"]["role"] == "owner"


@patch("app.services.cognito.boto3")
def test_login_wrong_password(mock_boto3, client):
    """Test login with incorrect credentials."""
    mock_cognito = MagicMock()
    mock_boto3.client.return_value = mock_cognito
    mock_cognito.initiate_auth.side_effect = _cognito_client_error(
        "NotAuthorizedException", "Incorrect username or password."
    )

    response = client.post(
        "/api/auth/login",
        json={
            "email": "user@example.com",
            "password": "WrongPass1!",
        },
    )
    assert response.status_code == 401
    assert "Incorrect email or password" in response.get_json()["error"]


@patch("app.services.cognito.boto3")
def test_login_unconfirmed_user(mock_boto3, client):
    """Test login when email is not yet confirmed."""
    mock_cognito = MagicMock()
    mock_boto3.client.return_value = mock_cognito
    mock_cognito.initiate_auth.side_effect = _cognito_client_error(
        "UserNotConfirmedException", "User is not confirmed."
    )

    response = client.post(
        "/api/auth/login",
        json={
            "email": "unconfirmed@example.com",
            "password": "Test1234!",
        },
    )
    assert response.status_code == 400
    assert "not verified" in response.get_json()["error"]


def test_login_missing_fields(client):
    """Test login with missing fields."""
    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com"},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Resend Code
# ---------------------------------------------------------------------------


@patch("app.services.cognito.boto3")
def test_resend_code_success(mock_boto3, client):
    """Test resending verification code."""
    mock_cognito = MagicMock()
    mock_boto3.client.return_value = mock_cognito
    mock_cognito.resend_confirmation_code.return_value = {}

    response = client.post(
        "/api/auth/resend-code",
        json={"email": "owner@example.com"},
    )
    assert response.status_code == 200
    assert response.get_json()["sent"] is True


@patch("app.services.cognito.boto3")
def test_resend_code_rate_limited(mock_boto3, client):
    """Test resend code when rate limited."""
    mock_cognito = MagicMock()
    mock_boto3.client.return_value = mock_cognito
    mock_cognito.resend_confirmation_code.side_effect = _cognito_client_error(
        "LimitExceededException", "Attempt limit exceeded, please try after some time."
    )

    response = client.post(
        "/api/auth/resend-code",
        json={"email": "owner@example.com"},
    )
    assert response.status_code == 400
    assert "Too many attempts" in response.get_json()["error"]


# ---------------------------------------------------------------------------
# Token Verification (require_cognito_auth decorator)
# ---------------------------------------------------------------------------


@patch("app.services.cognito.requests")
@patch("app.services.cognito.jwt")
@patch("app.services.cognito.jwk")
def test_cognito_token_verification(mock_jwk, mock_jwt, mock_requests, app):
    """Test the require_cognito_auth decorator with a valid token."""
    from app.auth import require_cognito_auth
    from flask import Blueprint, g, jsonify

    # Set up Cognito config
    app.config["COGNITO_USER_POOL_ID"] = "us-east-1_TestPool"
    app.config["COGNITO_CLIENT_ID"] = "testclientid123"
    app.config["COGNITO_REGION"] = "us-east-1"

    # Create a test route with Cognito auth
    test_bp = Blueprint("test_cognito", __name__)

    @test_bp.route("/test-cognito", methods=["GET"])
    @require_cognito_auth
    def test_route():
        return jsonify({
            "user_id": g.user_id,
            "role": g.user_role,
        })

    app.register_blueprint(test_bp, url_prefix="/api")

    # First create an owner user in DynamoDB
    with app.test_client() as test_client:
        with app.app_context():
            from app.services.user import create_owner_user

            create_owner_user(
                email="cognito@example.com",
                display_name="Cognito User",
                cognito_sub="sub-12345",
            )

        # Mock JWKS fetch
        mock_requests.get.return_value = MagicMock(
            json=MagicMock(return_value={
                "keys": [{"kid": "test-kid", "kty": "RSA"}]
            }),
            raise_for_status=MagicMock(),
        )

        # Mock JWT decode
        mock_jwt.get_unverified_header.return_value = {"kid": "test-kid"}
        mock_jwt.decode.return_value = {
            "sub": "sub-12345",
            "token_use": "access",
            "exp": 9999999999,
        }
        mock_jwk.construct.return_value = "mock-public-key"

        response = test_client.get(
            "/api/test-cognito",
            headers={"Authorization": "Bearer valid-cognito-token"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["role"] == "owner"


# ---------------------------------------------------------------------------
# Backward Compatibility — device token auth still works
# ---------------------------------------------------------------------------


def test_device_token_auth_still_works(client):
    """Ensure the existing invite-code registration and device token auth are intact."""
    # Register with invite code (old flow)
    reg = client.post(
        "/api/auth/register",
        json={
            "invite_code": "FAMILY",
            "device_name": "Test iPhone",
            "platform": "ios",
            "display_name": "Member User",
        },
    )
    assert reg.status_code == 201
    token = reg.get_json()["device_token"]

    # Verify token works
    response = client.post(
        "/api/auth/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["valid"] is True
    assert data["name"] == "Member User"


# ---------------------------------------------------------------------------
# Owner user creation in DynamoDB
# ---------------------------------------------------------------------------


@patch("app.services.cognito.boto3")
def test_signup_creates_owner_role(mock_boto3, client):
    """Test that signup creates a user with role=owner."""
    mock_cognito = MagicMock()
    mock_boto3.client.return_value = mock_cognito
    mock_cognito.sign_up.return_value = {"UserSub": "cognito-sub-owner"}

    response = client.post(
        "/api/auth/signup",
        json={
            "email": "newowner@example.com",
            "password": "Test1234!",
            "display_name": "New Owner",
        },
    )
    assert response.status_code == 201

    # Now mock login to check the user role
    mock_cognito.initiate_auth.return_value = {
        "AuthenticationResult": {
            "IdToken": "id-tok",
            "AccessToken": "access-tok",
            "RefreshToken": "refresh-tok",
        }
    }

    login_resp = client.post(
        "/api/auth/login",
        json={
            "email": "newowner@example.com",
            "password": "Test1234!",
        },
    )
    assert login_resp.status_code == 200
    assert login_resp.get_json()["user"]["role"] == "owner"


# ---------------------------------------------------------------------------
# Valid JWT but no matching DynamoDB user
# ---------------------------------------------------------------------------


@patch("app.services.cognito.requests")
@patch("app.services.cognito.jwt")
@patch("app.services.cognito.jwk")
def test_cognito_token_valid_but_no_dynamo_user(mock_jwk, mock_jwt, mock_requests, app):
    """Test that a valid Cognito JWT returns 401 when no matching DynamoDB user exists."""
    from app.auth import require_cognito_auth
    from flask import Blueprint, g, jsonify

    # Set up Cognito config
    app.config["COGNITO_USER_POOL_ID"] = "us-east-1_TestPool"
    app.config["COGNITO_CLIENT_ID"] = "testclientid123"
    app.config["COGNITO_REGION"] = "us-east-1"

    # Create a test route with Cognito auth
    test_bp = Blueprint("test_cognito_no_user", __name__)

    @test_bp.route("/test-cognito-no-user", methods=["GET"])
    @require_cognito_auth
    def test_route():
        return jsonify({"user_id": g.user_id})

    app.register_blueprint(test_bp, url_prefix="/api")

    with app.test_client() as test_client:
        # Mock JWKS fetch
        mock_requests.get.return_value = MagicMock(
            json=MagicMock(return_value={
                "keys": [{"kid": "test-kid", "kty": "RSA"}]
            }),
            raise_for_status=MagicMock(),
        )

        # Mock JWT decode with a sub that has no matching DynamoDB user
        mock_jwt.get_unverified_header.return_value = {"kid": "test-kid"}
        mock_jwt.decode.return_value = {
            "sub": "non-existent-sub-99999",
            "token_use": "access",
            "exp": 9999999999,
        }
        mock_jwk.construct.return_value = "mock-public-key"

        response = test_client.get(
            "/api/test-cognito-no-user",
            headers={"Authorization": "Bearer valid-but-orphaned-token"},
        )
        assert response.status_code == 401
        data = response.get_json()
        assert "error" in data
