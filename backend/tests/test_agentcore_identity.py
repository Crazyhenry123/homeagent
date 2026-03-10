"""Unit tests for AgentCoreIdentityMiddleware.

Tests JWT validation, require_auth decorator, require_role decorator,
and error handling for the Cognito-based identity middleware.
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import g, jsonify

from app.agentcore_identity import AgentCoreIdentityMiddleware, _JWKSCache


# ---------------------------------------------------------------------------
# Helpers: RSA key pair for signing test JWTs
# ---------------------------------------------------------------------------

_TEST_KID = "test-kid-001"
_TEST_POOL_ID = "us-east-1_TestPool"
_TEST_CLIENT_ID = "test-client-id"
_TEST_REGION = "us-east-1"
_TEST_ISSUER = f"https://cognito-idp.{_TEST_REGION}.amazonaws.com/{_TEST_POOL_ID}"


def _generate_rsa_keypair():
    """Generate an RSA private/public key pair for test JWT signing."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key


_PRIVATE_KEY = _generate_rsa_keypair()
_PUBLIC_KEY = _PRIVATE_KEY.public_key()


def _public_key_jwk() -> dict:
    """Return the public key as a JWK dict with kid."""
    from jwt.algorithms import RSAAlgorithm

    jwk = json.loads(RSAAlgorithm.to_jwk(_PUBLIC_KEY))
    jwk["kid"] = _TEST_KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return jwk


def _make_token(
    sub: str = "cognito-sub-123",
    exp_offset: int = 3600,
    iss: str | None = None,
    aud: str | None = None,
    kid: str | None = None,
    private_key=None,
) -> str:
    """Create a signed JWT for testing."""
    now = int(time.time())
    payload = {
        "sub": sub,
        "iss": iss or _TEST_ISSUER,
        "aud": aud or _TEST_CLIENT_ID,
        "exp": now + exp_offset,
        "iat": now,
        "token_use": "id",
    }
    headers = {"kid": kid or _TEST_KID}
    return pyjwt.encode(
        payload,
        private_key or _PRIVATE_KEY,
        algorithm="RS256",
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def jwks_response():
    """Mock JWKS endpoint response."""
    return {"keys": [_public_key_jwk()]}


@pytest.fixture()
def mock_jwks(jwks_response):
    """Patch requests.get to return our test JWKS."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = jwks_response
    mock_resp.raise_for_status = MagicMock()
    with patch("app.agentcore_identity.requests.get", return_value=mock_resp) as m:
        yield m


@pytest.fixture()
def middleware(mock_jwks):
    """Create a middleware instance with mocked JWKS fetching."""
    return AgentCoreIdentityMiddleware(
        cognito_user_pool_id=_TEST_POOL_ID,
        cognito_client_id=_TEST_CLIENT_ID,
        region=_TEST_REGION,
    )


@pytest.fixture()
def mock_dal():
    """Patch get_dal() to return a mock DAL with users/devices/memberships repos."""
    dal = MagicMock()
    with patch("app.agentcore_identity.get_dal", return_value=dal):
        yield dal


@pytest.fixture()
def registered_user(mock_dal):
    """Configure mock DAL to return a registered user."""
    user_item = {
        "user_id": "usr_01ABC",
        "cognito_sub": "cognito-sub-123",
        "family_id": "fam_01XYZ",
        "name": "Alice",
        "role": "admin",
    }
    mock_dal.users.get_by_cognito_sub.return_value = user_item
    return user_item


# ---------------------------------------------------------------------------
# Tests: validate_token
# ---------------------------------------------------------------------------


class TestValidateToken:
    """Tests for AgentCoreIdentityMiddleware.validate_token()."""

    def test_valid_token_returns_identity(self, middleware, mock_dal, registered_user):
        token = _make_token(sub="cognito-sub-123")
        identity = middleware.validate_token(token)

        assert identity.user_id == "usr_01ABC"
        assert identity.family_id == "fam_01XYZ"
        assert identity.role == "admin"
        assert identity.cognito_sub == "cognito-sub-123"

    def test_expired_token_raises(self, middleware, mock_dal):
        token = _make_token(exp_offset=-3600)  # Already expired
        with pytest.raises(pyjwt.ExpiredSignatureError):
            middleware.validate_token(token)

    def test_malformed_token_raises(self, middleware):
        with pytest.raises(pyjwt.InvalidTokenError):
            middleware.validate_token("not-a-jwt")

    def test_wrong_issuer_raises(self, middleware, mock_dal):
        token = _make_token(iss="https://evil.example.com")
        with pytest.raises(pyjwt.InvalidTokenError):
            middleware.validate_token(token)

    def test_wrong_audience_raises(self, middleware, mock_dal):
        token = _make_token(aud="wrong-client-id")
        with pytest.raises(pyjwt.InvalidTokenError):
            middleware.validate_token(token)

    def test_unknown_kid_raises(self, middleware):
        token = _make_token(kid="unknown-kid")
        with pytest.raises(pyjwt.InvalidTokenError, match="Unknown signing key"):
            middleware.validate_token(token)

    def test_user_not_registered_raises(self, middleware, mock_dal):
        mock_dal.users.get_by_cognito_sub.return_value = None
        token = _make_token(sub="unknown-sub")
        with pytest.raises(LookupError, match="User not registered"):
            middleware.validate_token(token)

    def test_member_role_default(self, middleware, mock_dal):
        """User without explicit role defaults to 'member'."""
        mock_dal.users.get_by_cognito_sub.return_value = {
            "user_id": "usr_02DEF",
            "cognito_sub": "cognito-sub-456",
            "name": "Bob",
            # no 'role' key
        }
        token = _make_token(sub="cognito-sub-456")
        identity = middleware.validate_token(token)
        assert identity.role == "member"
        assert identity.family_id is None


# ---------------------------------------------------------------------------
# Tests: require_auth decorator
# ---------------------------------------------------------------------------


class TestRequireAuth:
    """Tests for the require_auth decorator via Flask test client."""

    def _make_app_with_route(self, middleware):
        """Create a minimal Flask app with a protected route."""
        from flask import Flask, jsonify

        app = Flask(__name__)
        app.config["TESTING"] = True

        @app.route("/protected")
        @middleware.require_auth
        def protected():
            return jsonify(
                {
                    "user_id": g.user_id,
                    "family_id": g.family_id,
                    "user_role": g.user_role,
                    "cognito_sub": g.cognito_sub,
                }
            )

        return app

    def test_valid_token_sets_context(self, middleware, mock_dal, registered_user):
        app = self._make_app_with_route(middleware)
        token = _make_token(sub="cognito-sub-123")
        with app.test_client() as c:
            resp = c.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user_id"] == "usr_01ABC"
        assert data["family_id"] == "fam_01XYZ"
        assert data["user_role"] == "admin"
        assert data["cognito_sub"] == "cognito-sub-123"

    def test_missing_auth_header_returns_401(self, middleware):
        app = self._make_app_with_route(middleware)
        with app.test_client() as c:
            resp = c.get("/protected")
        assert resp.status_code == 401
        assert "Missing or invalid" in resp.get_json()["error"]

    def test_non_bearer_header_returns_401(self, middleware):
        app = self._make_app_with_route(middleware)
        with app.test_client() as c:
            resp = c.get("/protected", headers={"Authorization": "Basic abc123"})
        assert resp.status_code == 401

    def test_empty_bearer_token_returns_401(self, middleware):
        app = self._make_app_with_route(middleware)
        with app.test_client() as c:
            resp = c.get("/protected", headers={"Authorization": "Bearer "})
        assert resp.status_code == 401

    def test_expired_token_returns_401_with_code(self, middleware, mock_dal):
        app = self._make_app_with_route(middleware)
        token = _make_token(exp_offset=-3600)
        with app.test_client() as c:
            resp = c.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["code"] == "TOKEN_EXPIRED"

    def test_invalid_token_returns_401(self, middleware, mock_dal):
        """Invalid JWT falls through to device-token lookup (dual-auth).
        Device-token also fails → 401."""
        mock_dal.devices.get_by_token.return_value = None
        app = self._make_app_with_route(middleware)
        with app.test_client() as c:
            resp = c.get("/protected", headers={"Authorization": "Bearer not-a-jwt"})
        assert resp.status_code == 401

    def test_unregistered_user_returns_401(self, middleware, mock_dal):
        mock_dal.users.get_by_cognito_sub.return_value = None
        app = self._make_app_with_route(middleware)
        token = _make_token(sub="unknown-sub")
        with app.test_client() as c:
            resp = c.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert "User not registered" in resp.get_json()["error"]

    # ---------------------------------------------------------------------------
    # Tests: dual-auth mode (Requirements 19.5, 31.5)
    # ---------------------------------------------------------------------------

    class TestDualAuthMode:
        """Tests for dual-auth: JWT first, device-token fallback."""

        def _make_app_with_route(self, middleware):
            from flask import Flask

            app = Flask(__name__)
            app.config["TESTING"] = True

            @app.route("/protected")
            @middleware.require_auth
            def protected():
                return jsonify(
                    {
                        "user_id": g.user_id,
                        "family_id": g.get("family_id"),
                        "user_role": g.user_role,
                        "cognito_sub": g.get("cognito_sub"),
                        "device_id": g.get("device_id"),
                    }
                )

            return app

        def test_device_token_fallback_succeeds(self, middleware, mock_dal):
            """When JWT validation fails, device-token lookup succeeds."""
            device_item = {
                "device_id": "dev_001",
                "user_id": "usr_legacy",
                "device_token": "legacy-device-token",
            }
            user_item = {
                "user_id": "usr_legacy",
                "name": "LegacyUser",
                "role": "member",
                "family_id": "fam_legacy",
            }

            mock_dal.devices.get_by_token.return_value = device_item
            mock_dal.users.get_by_id.return_value = user_item

            app = self._make_app_with_route(middleware)
            with app.test_client() as c:
                resp = c.get(
                    "/protected",
                    headers={"Authorization": "Bearer legacy-device-token"},
                )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["user_id"] == "usr_legacy"
            assert data["user_role"] == "member"
            assert data["family_id"] == "fam_legacy"
            assert data["cognito_sub"] is None
            assert data["device_id"] == "dev_001"

        def test_device_token_fallback_no_device_returns_401(
            self, middleware, mock_dal
        ):
            """When JWT fails and device-token not found, returns 401."""
            mock_dal.devices.get_by_token.return_value = None

            app = self._make_app_with_route(middleware)
            with app.test_client() as c:
                resp = c.get(
                    "/protected",
                    headers={"Authorization": "Bearer unknown-token"},
                )

            assert resp.status_code == 401
            assert "Invalid token" in resp.get_json()["error"]

        def test_device_token_fallback_no_user_returns_401(self, middleware, mock_dal):
            """When device found but user missing, returns 401."""
            device_item = {
                "device_id": "dev_orphan",
                "user_id": "usr_deleted",
                "device_token": "orphan-token",
            }
            mock_dal.devices.get_by_token.return_value = device_item
            mock_dal.users.get_by_id.return_value = None

            app = self._make_app_with_route(middleware)
            with app.test_client() as c:
                resp = c.get(
                    "/protected",
                    headers={"Authorization": "Bearer orphan-token"},
                )

            assert resp.status_code == 401
            assert "User not found" in resp.get_json()["error"]

        def test_expired_jwt_does_not_fallback(self, middleware, mock_dal):
            """Expired JWT returns TOKEN_EXPIRED without trying device-token."""
            app = self._make_app_with_route(middleware)
            token = _make_token(exp_offset=-3600)

            with app.test_client() as c:
                resp = c.get(
                    "/protected",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert resp.status_code == 401
            assert resp.get_json()["code"] == "TOKEN_EXPIRED"
            # DAL devices should NOT have been called for device-token lookup
            mock_dal.devices.get_by_token.assert_not_called()

        def test_valid_jwt_takes_priority_over_device_token(
            self, middleware, mock_dal, registered_user
        ):
            """Valid JWT succeeds without touching device-token path."""
            app = self._make_app_with_route(middleware)
            token = _make_token(sub="cognito-sub-123")

            with app.test_client() as c:
                resp = c.get(
                    "/protected",
                    headers={"Authorization": f"Bearer {token}"},
                )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["user_id"] == "usr_01ABC"
            assert data["cognito_sub"] == "cognito-sub-123"
            assert data.get("device_id") is None


# ---------------------------------------------------------------------------
# Tests: require_role decorator
# ---------------------------------------------------------------------------


class TestRequireRole:
    """Tests for the require_role decorator."""

    def _make_app_with_admin_route(self, middleware):
        from flask import Flask, jsonify

        app = Flask(__name__)
        app.config["TESTING"] = True

        @app.route("/admin-only")
        @middleware.require_auth
        @middleware.require_role("admin")
        def admin_only():
            return jsonify({"ok": True})

        return app

    def test_admin_role_allowed(self, middleware, mock_dal, registered_user):
        """Admin user can access admin-only route."""
        app = self._make_app_with_admin_route(middleware)
        token = _make_token(sub="cognito-sub-123")
        with app.test_client() as c:
            resp = c.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_member_role_forbidden(self, middleware, mock_dal):
        """Member user gets 403 on admin-only route."""
        mock_dal.users.get_by_cognito_sub.return_value = {
            "user_id": "usr_member",
            "cognito_sub": "cognito-sub-member",
            "role": "member",
        }
        app = self._make_app_with_admin_route(middleware)
        token = _make_token(sub="cognito-sub-member")
        with app.test_client() as c:
            resp = c.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403
        assert "Forbidden" in resp.get_json()["error"]


# ---------------------------------------------------------------------------
# Tests: get_identity_context
# ---------------------------------------------------------------------------


class TestGetIdentityContext:
    """Tests for get_identity_context()."""

    def test_returns_context_from_g(self, middleware, mock_dal, registered_user):
        from flask import Flask

        app = Flask(__name__)
        app.config["TESTING"] = True

        @app.route("/ctx")
        @middleware.require_auth
        def ctx_route():
            ctx = middleware.get_identity_context()
            return jsonify(
                {
                    "user_id": ctx.user_id,
                    "family_id": ctx.family_id,
                    "role": ctx.role,
                    "cognito_sub": ctx.cognito_sub,
                }
            )

        token = _make_token(sub="cognito-sub-123")
        with app.test_client() as c:
            resp = c.get("/ctx", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user_id"] == "usr_01ABC"
        assert data["cognito_sub"] == "cognito-sub-123"


# ---------------------------------------------------------------------------
# Tests: JWKS caching
# ---------------------------------------------------------------------------


class TestJWKSCache:
    """Tests for the _JWKSCache helper."""

    def test_cache_refreshes_after_ttl(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"keys": [_public_key_jwk()]}
        mock_resp.raise_for_status = MagicMock()

        with patch("app.agentcore_identity.requests.get", return_value=mock_resp):
            cache = _JWKSCache("https://example.com/jwks", ttl_seconds=1)
            key1 = cache.get_key(_TEST_KID)
            assert key1 is not None

            # Within TTL — no re-fetch
            call_count_after_first = mock_resp.json.call_count
            key2 = cache.get_key(_TEST_KID)
            assert mock_resp.json.call_count == call_count_after_first

            # Force staleness
            cache._fetched_at = time.time() - 2
            key3 = cache.get_key(_TEST_KID)
            assert mock_resp.json.call_count > call_count_after_first

    def test_unknown_kid_returns_none(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"keys": [_public_key_jwk()]}
        mock_resp.raise_for_status = MagicMock()

        with patch("app.agentcore_identity.requests.get", return_value=mock_resp):
            cache = _JWKSCache("https://example.com/jwks", ttl_seconds=3600)
            assert cache.get_key("nonexistent-kid") is None


# ---------------------------------------------------------------------------
# Tests: family group resolution (Requirements 24.1, 24.2)
# ---------------------------------------------------------------------------


class TestFamilyGroupResolution:
    """Tests for _resolve_family_group and its integration into require_auth."""

    def _make_app_with_route(self, middleware):
        from flask import Flask

        app = Flask(__name__)
        app.config["TESTING"] = True

        @app.route("/protected")
        @middleware.require_auth
        def protected():
            return jsonify(
                {
                    "user_id": g.user_id,
                    "family_id": g.family_id,
                    "user_role": g.user_role,
                    "cognito_sub": g.cognito_sub,
                }
            )

        return app

    def test_existing_family_group_resolved(self, middleware):
        """User with existing FamilyGroups entry gets family_id from GSI."""
        user_item = {
            "user_id": "usr_01ABC",
            "cognito_sub": "cognito-sub-123",
            "name": "Alice",
            "role": "admin",
            # No family_id on user record — must come from FamilyGroups
        }
        family_item = {
            "family_id": "fam_existing",
            "member_id": "usr_01ABC",
            "role": "admin",
        }

        mock_dal = MagicMock()
        mock_dal.users.get_by_cognito_sub.return_value = user_item
        mock_dal.memberships._table.query.return_value = {"Items": [family_item]}

        app = self._make_app_with_route(middleware)
        token = _make_token(sub="cognito-sub-123")

        with patch("app.agentcore_identity.get_dal", return_value=mock_dal):
            with app.test_client() as c:
                resp = c.get(
                    "/protected",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["family_id"] == "fam_existing"

    def test_auto_creates_family_group_when_none_exists(self, middleware):
        """User without family group gets one auto-created (Req 24.2)."""
        user_item = {
            "user_id": "usr_new",
            "cognito_sub": "cognito-sub-new",
            "name": "NewUser",
            "role": "member",
        }

        mock_dal = MagicMock()
        mock_dal.users.get_by_cognito_sub.return_value = user_item
        mock_family_table = mock_dal.memberships._table
        mock_family_table.query.return_value = {"Items": []}  # No family group

        app = self._make_app_with_route(middleware)
        token = _make_token(sub="cognito-sub-new")

        with patch("app.agentcore_identity.get_dal", return_value=mock_dal):
            with app.test_client() as c:
                resp = c.get(
                    "/protected",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        data = resp.get_json()
        # Auto-created family_id should start with "fam_"
        assert data["family_id"] is not None
        assert data["family_id"].startswith("fam_")

        # Verify put_item was called to create the family group
        mock_family_table.put_item.assert_called_once()
        put_args = mock_family_table.put_item.call_args
        item = put_args[1]["Item"] if "Item" in put_args[1] else put_args[0][0]
        assert item["member_id"] == "usr_new"
        assert item["role"] == "member"
        assert "joined_at" in item

    def test_family_id_from_user_record_takes_precedence(self, middleware):
        """When user already has family_id on their record, skip resolution."""
        user_item = {
            "user_id": "usr_01ABC",
            "cognito_sub": "cognito-sub-123",
            "family_id": "fam_from_user",
            "name": "Alice",
            "role": "admin",
        }

        mock_dal = MagicMock()
        mock_dal.users.get_by_cognito_sub.return_value = user_item
        mock_family_table = mock_dal.memberships._table

        app = self._make_app_with_route(middleware)
        token = _make_token(sub="cognito-sub-123")

        with patch("app.agentcore_identity.get_dal", return_value=mock_dal):
            with app.test_client() as c:
                resp = c.get(
                    "/protected",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["family_id"] == "fam_from_user"
        # FamilyGroups table should NOT have been queried
        mock_family_table.query.assert_not_called()

    def test_family_lookup_failure_proceeds_with_none(self, middleware):
        """When FamilyGroups lookup fails, proceed with family_id=None (Req 24.1)."""
        user_item = {
            "user_id": "usr_fail",
            "cognito_sub": "cognito-sub-fail",
            "name": "FailUser",
            "role": "member",
        }

        mock_dal = MagicMock()
        mock_dal.users.get_by_cognito_sub.return_value = user_item
        mock_dal.memberships._table.query.side_effect = Exception(
            "DynamoDB unavailable"
        )

        app = self._make_app_with_route(middleware)
        token = _make_token(sub="cognito-sub-fail")

        with patch("app.agentcore_identity.get_dal", return_value=mock_dal):
            with app.test_client() as c:
                resp = c.get(
                    "/protected",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["family_id"] is None

    def test_device_token_fallback_resolves_family_group(self, middleware):
        """Device-token auth path also resolves family group when missing."""
        device_item = {
            "device_id": "dev_001",
            "user_id": "usr_legacy",
            "device_token": "legacy-token",
        }
        user_item = {
            "user_id": "usr_legacy",
            "name": "LegacyUser",
            "role": "member",
            # No family_id
        }
        family_item = {
            "family_id": "fam_legacy_resolved",
            "member_id": "usr_legacy",
            "role": "member",
        }

        mock_dal = MagicMock()
        mock_dal.devices.get_by_token.return_value = device_item
        mock_dal.users.get_by_id.return_value = user_item
        mock_dal.memberships._table.query.return_value = {"Items": [family_item]}

        app = self._make_app_with_route(middleware)

        with patch("app.agentcore_identity.get_dal", return_value=mock_dal):
            with app.test_client() as c:
                resp = c.get(
                    "/protected",
                    headers={"Authorization": "Bearer legacy-token"},
                )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["family_id"] == "fam_legacy_resolved"
