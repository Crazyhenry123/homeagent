"""Property-based tests for AgentCore Identity Middleware authentication.

Uses Hypothesis to verify Property 13: Authentication Token Validation.

**Validates: Requirements 17.1, 17.2, 17.3, 17.4, 17.6**

Property 13: Authentication Token Validation — for any request with
Authorization header, valid JWT sets all four context fields;
missing/malformed/invalid/expired tokens return 401.
"""

from __future__ import annotations

import json
import string
import time
from unittest.mock import MagicMock, patch

import jwt as pyjwt
from flask import Flask, g, jsonify
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.agentcore_identity import AgentCoreIdentityMiddleware

# ---------------------------------------------------------------------------
# RSA key pair for signing test JWTs
# ---------------------------------------------------------------------------

_TEST_KID = "prop-test-kid"
_TEST_POOL_ID = "us-east-1_PropPool"
_TEST_CLIENT_ID = "prop-client-id"
_TEST_REGION = "us-east-1"
_TEST_ISSUER = f"https://cognito-idp.{_TEST_REGION}.amazonaws.com/{_TEST_POOL_ID}"

from cryptography.hazmat.primitives.asymmetric import rsa

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_WRONG_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _public_key_jwk() -> dict:
    jwk = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(_PUBLIC_KEY))
    jwk["kid"] = _TEST_KID
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return jwk


def _make_token(
    sub: str,
    exp_offset: int = 3600,
    iss: str | None = None,
    aud: str | None = None,
    kid: str | None = None,
    private_key=None,
) -> str:
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


def _create_middleware():
    """Create middleware with mocked JWKS — call inside a patch context."""
    return AgentCoreIdentityMiddleware(
        cognito_user_pool_id=_TEST_POOL_ID,
        cognito_client_id=_TEST_CLIENT_ID,
        region=_TEST_REGION,
    )


def _mock_jwks_response():
    """Return a mock for requests.get that serves our test JWKS."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"keys": [_public_key_jwk()]}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _make_flask_app(mw):
    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.route("/protected")
    @mw.require_auth
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


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_user_id_st = st.text(
    alphabet=string.ascii_lowercase + string.digits + "_",
    min_size=3,
    max_size=20,
).map(lambda s: f"usr_{s}")

_family_id_st = st.one_of(
    st.none(),
    st.text(
        alphabet=string.ascii_lowercase + string.digits + "_",
        min_size=3,
        max_size=20,
    ).map(lambda s: f"fam_{s}"),
)

_role_st = st.sampled_from(["admin", "member"])

_cognito_sub_st = st.text(
    alphabet=string.hexdigits + "-",
    min_size=8,
    max_size=36,
).filter(lambda s: s.strip() and not s.startswith("-"))

_malformed_token_st = st.text(
    alphabet=string.ascii_letters + string.digits + "!@#$%^&*",
    min_size=1,
    max_size=100,
)


# ---------------------------------------------------------------------------
# Property 13: Authentication Token Validation
# Validates: Requirements 17.1, 17.2, 17.3, 17.4, 17.6
# ---------------------------------------------------------------------------


class TestAuthTokenValidation:
    """**Validates: Requirements 17.1, 17.2, 17.3, 17.4, 17.6**

    Property 13: Authentication Token Validation — for any request with
    Authorization header, valid JWT sets all four context fields;
    missing/malformed/invalid/expired tokens return 401.
    """

    @given(
        user_id=_user_id_st,
        family_id=_family_id_st,
        role=_role_st,
        cognito_sub=_cognito_sub_st,
    )
    @settings(
        max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_valid_jwt_sets_all_four_context_fields(
        self,
        user_id: str,
        family_id: str | None,
        role: str,
        cognito_sub: str,
    ) -> None:
        """Requirement 17.1, 17.2, 17.3: For any valid Bearer JWT, the
        middleware validates the token and sets g.user_id, g.family_id,
        g.user_role, and g.cognito_sub on the Flask request context.
        """
        user_item = {
            "user_id": user_id,
            "cognito_sub": cognito_sub,
            "family_id": family_id,
            "role": role,
        }
        mock_dal = MagicMock()
        mock_dal.users.get_by_cognito_sub.return_value = user_item
        # Configure memberships table for family group resolution when
        # family_id is None on the user record.
        if family_id is not None:
            mock_dal.memberships._table.query.return_value = {
                "Items": [{"family_id": family_id, "member_id": user_id}],
            }
        else:
            mock_dal.memberships._table.query.return_value = {"Items": []}

        token = _make_token(sub=cognito_sub)

        with patch(
            "app.agentcore_identity.requests.get", return_value=_mock_jwks_response()
        ):
            mw = _create_middleware()
            app = _make_flask_app(mw)
            with patch("app.agentcore_identity.get_dal", return_value=mock_dal):
                with app.test_client() as c:
                    resp = c.get(
                        "/protected",
                        headers={"Authorization": f"Bearer {token}"},
                    )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["user_id"] == user_id
        if family_id is not None:
            assert data["family_id"] == family_id
        else:
            # Auto-created family group
            assert data["family_id"] is not None
            assert data["family_id"].startswith("fam_")
        assert data["user_role"] == role
        assert data["cognito_sub"] == cognito_sub

    @given(
        header_name=st.text(
            alphabet=string.ascii_letters, min_size=1, max_size=20
        ).filter(lambda s: s.lower() != "authorization"),
    )
    @settings(
        max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_missing_authorization_header_returns_401(
        self,
        header_name: str,
    ) -> None:
        """Requirement 17.4: Requests without an Authorization header
        return HTTP 401.
        """
        with patch(
            "app.agentcore_identity.requests.get", return_value=_mock_jwks_response()
        ):
            mw = _create_middleware()
            app = _make_flask_app(mw)
            with app.test_client() as c:
                resp = c.get("/protected", headers={header_name: "some-value"})

        assert resp.status_code == 401

    @given(
        prefix=st.sampled_from(["Basic ", "Token ", "Digest ", "MAC ", ""]),
        value=st.text(min_size=0, max_size=50).filter(
            lambda s: "\r" not in s and "\n" not in s
        ),
    )
    @settings(
        max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_non_bearer_auth_header_returns_401(
        self,
        prefix: str,
        value: str,
    ) -> None:
        """Requirement 17.4: Authorization headers that don't start with
        'Bearer ' return HTTP 401.
        """
        auth_value = prefix + value

        with patch(
            "app.agentcore_identity.requests.get", return_value=_mock_jwks_response()
        ):
            mw = _create_middleware()
            app = _make_flask_app(mw)
            with app.test_client() as c:
                resp = c.get(
                    "/protected",
                    headers={"Authorization": auth_value},
                )

        assert resp.status_code == 401

    @given(malformed_token=_malformed_token_st)
    @settings(
        max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_malformed_token_returns_401(
        self,
        malformed_token: str,
    ) -> None:
        """Requirement 17.6: Malformed tokens (random strings that are
        not valid JWTs) return HTTP 401.

        With dual-auth mode, malformed JWTs fall through to device-token
        lookup which also fails → 401.
        """
        mock_dal = MagicMock()
        mock_dal.devices.get_by_token.return_value = None

        with (
            patch(
                "app.agentcore_identity.requests.get",
                return_value=_mock_jwks_response(),
            ),
            patch("app.agentcore_identity.get_dal", return_value=mock_dal),
        ):
            mw = _create_middleware()
            app = _make_flask_app(mw)
            with app.test_client() as c:
                resp = c.get(
                    "/protected",
                    headers={"Authorization": f"Bearer {malformed_token}"},
                )

        assert resp.status_code == 401

    @given(
        cognito_sub=_cognito_sub_st,
        seconds_expired=st.integers(min_value=1, max_value=86400),
    )
    @settings(
        max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_expired_token_returns_401_with_token_expired_code(
        self,
        cognito_sub: str,
        seconds_expired: int,
    ) -> None:
        """Requirement 17.5: Expired tokens return HTTP 401 with error
        code TOKEN_EXPIRED.
        """
        token = _make_token(sub=cognito_sub, exp_offset=-seconds_expired)

        with patch(
            "app.agentcore_identity.requests.get", return_value=_mock_jwks_response()
        ):
            mw = _create_middleware()
            app = _make_flask_app(mw)
            with app.test_client() as c:
                resp = c.get(
                    "/protected",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 401
        data = resp.get_json()
        assert data["code"] == "TOKEN_EXPIRED"

    @given(cognito_sub=_cognito_sub_st)
    @settings(
        max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_token_signed_with_unknown_key_returns_401(
        self,
        cognito_sub: str,
    ) -> None:
        """Requirement 17.6: Tokens signed by an unknown provider
        (wrong key) return HTTP 401.

        With dual-auth mode, unknown-key JWTs fall through to device-token
        lookup which also fails → 401.
        """
        token = _make_token(
            sub=cognito_sub,
            kid="unknown-kid-xyz",
            private_key=_WRONG_PRIVATE_KEY,
        )

        mock_dal = MagicMock()
        mock_dal.devices.get_by_token.return_value = None

        with (
            patch(
                "app.agentcore_identity.requests.get",
                return_value=_mock_jwks_response(),
            ),
            patch("app.agentcore_identity.get_dal", return_value=mock_dal),
        ):
            mw = _create_middleware()
            app = _make_flask_app(mw)
            with app.test_client() as c:
                resp = c.get(
                    "/protected",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Helpers for Property 14: Role-Based Access Enforcement
# ---------------------------------------------------------------------------


def _make_role_flask_app(mw, required_role: str):
    """Create a Flask app with a route that requires a specific role."""
    app = Flask(__name__)
    app.config["TESTING"] = True

    @app.route("/role-protected")
    @mw.require_auth
    @mw.require_role(required_role)
    def role_protected():
        return jsonify({"ok": True})

    return app


def _authenticated_request(user_role: str, required_role: str) -> int:
    """Issue a request as a user with *user_role* to a route requiring
    *required_role* and return the HTTP status code."""
    cognito_sub = "test-sub-role-check"
    user_item = {
        "user_id": "usr_role_tester",
        "cognito_sub": cognito_sub,
        "family_id": "fam_role_test",
        "role": user_role,
    }
    mock_dal = MagicMock()
    mock_dal.users.get_by_cognito_sub.return_value = user_item

    token = _make_token(sub=cognito_sub)

    with patch(
        "app.agentcore_identity.requests.get", return_value=_mock_jwks_response()
    ):
        mw = _create_middleware()
        app = _make_role_flask_app(mw, required_role)
        with patch("app.agentcore_identity.get_dal", return_value=mock_dal):
            with app.test_client() as c:
                resp = c.get(
                    "/role-protected",
                    headers={"Authorization": f"Bearer {token}"},
                )
    return resp.status_code


# ---------------------------------------------------------------------------
# Property 14: Role-Based Access Enforcement
# Validates: Requirements 18.1, 18.2
# ---------------------------------------------------------------------------


class TestRoleBasedAccessEnforcement:
    """**Validates: Requirements 18.1, 18.2**

    Property 14: Role-Based Access Enforcement — for any authenticated
    user whose role does not match a route's required role, middleware
    returns 403.
    """

    @given(
        user_id=_user_id_st,
        family_id=_family_id_st,
        cognito_sub=_cognito_sub_st,
        required_role=_role_st,
    )
    @settings(
        max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_matching_role_grants_access(
        self,
        user_id: str,
        family_id: str | None,
        cognito_sub: str,
        required_role: str,
    ) -> None:
        """Requirement 18.1, 18.2: When the user's role matches the
        route's required role, the request succeeds with 200.
        """
        user_item = {
            "user_id": user_id,
            "cognito_sub": cognito_sub,
            "family_id": family_id,
            "role": required_role,  # role matches requirement
        }
        mock_dal = MagicMock()
        mock_dal.users.get_by_cognito_sub.return_value = user_item

        token = _make_token(sub=cognito_sub)

        with patch(
            "app.agentcore_identity.requests.get", return_value=_mock_jwks_response()
        ):
            mw = _create_middleware()
            app = _make_role_flask_app(mw, required_role)
            with patch("app.agentcore_identity.get_dal", return_value=mock_dal):
                with app.test_client() as c:
                    resp = c.get(
                        "/role-protected",
                        headers={"Authorization": f"Bearer {token}"},
                    )

        assert resp.status_code == 200

    @given(
        user_id=_user_id_st,
        family_id=_family_id_st,
        cognito_sub=_cognito_sub_st,
        user_role=_role_st,
        required_role=_role_st,
    )
    @settings(
        max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_mismatched_role_returns_403(
        self,
        user_id: str,
        family_id: str | None,
        cognito_sub: str,
        user_role: str,
        required_role: str,
    ) -> None:
        """Requirement 18.2: When the user's role does NOT match the
        route's required role, the middleware returns 403.
        """
        from hypothesis import assume

        assume(user_role != required_role)

        user_item = {
            "user_id": user_id,
            "cognito_sub": cognito_sub,
            "family_id": family_id,
            "role": user_role,
        }
        mock_dal = MagicMock()
        mock_dal.users.get_by_cognito_sub.return_value = user_item

        token = _make_token(sub=cognito_sub)

        with patch(
            "app.agentcore_identity.requests.get", return_value=_mock_jwks_response()
        ):
            mw = _create_middleware()
            app = _make_role_flask_app(mw, required_role)
            with patch("app.agentcore_identity.get_dal", return_value=mock_dal):
                with app.test_client() as c:
                    resp = c.get(
                        "/role-protected",
                        headers={"Authorization": f"Bearer {token}"},
                    )

        assert resp.status_code == 403

    def test_member_accessing_admin_route_returns_403(self) -> None:
        """Requirement 18.2: A user with role 'member' accessing an
        admin-required route gets 403.
        """
        status = _authenticated_request(user_role="member", required_role="admin")
        assert status == 403

    def test_admin_accessing_admin_route_returns_200(self) -> None:
        """Requirement 18.1: A user with role 'admin' accessing an
        admin-required route gets 200.
        """
        status = _authenticated_request(user_role="admin", required_role="admin")
        assert status == 200

    def test_admin_accessing_member_route_returns_403(self) -> None:
        """Requirement 18.2: A user with role 'admin' accessing a
        member-required route gets 403 (strict match).
        """
        status = _authenticated_request(user_role="admin", required_role="member")
        assert status == 403

    def test_member_accessing_member_route_returns_200(self) -> None:
        """Requirement 18.1: A user with role 'member' accessing a
        member-required route gets 200.
        """
        status = _authenticated_request(user_role="member", required_role="member")
        assert status == 200


# ---------------------------------------------------------------------------
# Property 22: Family Membership Validation
# Validates: Requirements 12.5, 24.1
# ---------------------------------------------------------------------------


class TestFamilyMembershipValidation:
    """**Validates: Requirements 12.5, 24.1**

    Property 22: Family Membership Validation — for any (family_id,
    member_id) pair, system verifies membership; users without family_id
    proceed with member-only memory.
    """

    @given(
        user_id=_user_id_st,
        family_id=_family_id_st.filter(lambda s: s is not None),
        role=_role_st,
    )
    @settings(
        max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_existing_family_group_resolves_correct_family_id(
        self,
        user_id: str,
        family_id: str,
        role: str,
    ) -> None:
        """Requirement 12.5: For any user with an existing family group
        mapping in FamilyGroups table, _resolve_family_group returns the
        correct family_id from the member-family-index GSI.
        """
        family_item = {
            "family_id": family_id,
            "member_id": user_id,
            "role": role,
        }
        mock_dal = MagicMock()
        mock_dal.memberships._table.query.return_value = {"Items": [family_item]}

        with patch("app.agentcore_identity.get_dal", return_value=mock_dal):
            result = AgentCoreIdentityMiddleware._resolve_family_group(user_id, role)

        assert result == family_id
        mock_dal.memberships._table.query.assert_called_once_with(
            IndexName="member-family-index",
            KeyConditionExpression="member_id = :uid",
            ExpressionAttributeValues={":uid": user_id},
            Limit=1,
        )

    @given(
        user_id=_user_id_st,
        role=_role_st,
    )
    @settings(
        max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_no_family_group_auto_creates_single_member_group(
        self,
        user_id: str,
        role: str,
    ) -> None:
        """Requirement 24.1: For any user without a family group mapping,
        the system auto-creates a single-member family group and returns
        a new family_id starting with 'fam_'.
        """
        mock_dal = MagicMock()
        mock_dal.memberships._table.query.return_value = {"Items": []}

        with patch("app.agentcore_identity.get_dal", return_value=mock_dal):
            result = AgentCoreIdentityMiddleware._resolve_family_group(user_id, role)

        assert result is not None
        assert result.startswith("fam_")

        mock_dal.memberships._table.put_item.assert_called_once()
        put_kwargs = mock_dal.memberships._table.put_item.call_args[1]
        item = put_kwargs["Item"]
        assert item["family_id"] == result
        assert item["member_id"] == user_id
        assert item["role"] == role
        assert "joined_at" in item

    @given(
        user_id=_user_id_st,
        role=_role_st,
    )
    @settings(
        max_examples=10, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_family_lookup_failure_returns_none_for_member_only_memory(
        self,
        user_id: str,
        role: str,
    ) -> None:
        """Requirement 24.1: For any user where the FamilyGroups table
        lookup fails, the system returns family_id=None so the user
        proceeds with member-only memory.
        """
        mock_dal = MagicMock()
        mock_dal.memberships._table.query.side_effect = Exception(
            "DynamoDB unavailable"
        )

        with patch("app.agentcore_identity.get_dal", return_value=mock_dal):
            result = AgentCoreIdentityMiddleware._resolve_family_group(user_id, role)

        assert result is None
