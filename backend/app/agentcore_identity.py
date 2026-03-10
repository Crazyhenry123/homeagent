"""AgentCore Identity Middleware for Cognito JWT authentication.

Replaces device-token auth (auth.py) with Cognito JWT validation.
Maps Cognito user attributes to the application's user/family/role model.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

import jwt
import requests
from flask import g, jsonify, request
from ulid import ULID

from app.dal import get_dal
from app.models.agentcore import IdentityContext

logger = logging.getLogger(__name__)


class _JWKSCache:
    """Thread-safe cache for Cognito JWKS keys with configurable TTL."""

    def __init__(self, jwks_url: str, ttl_seconds: int = 3600):
        self._jwks_url = jwks_url
        self._ttl_seconds = ttl_seconds
        self._keys: dict[str, dict[str, Any]] = {}
        self._fetched_at: float = 0.0
        self._lock = threading.Lock()

    def get_key(self, kid: str) -> dict[str, Any] | None:
        """Return the JWK for the given key ID, refreshing if stale."""
        if self._is_stale() or kid not in self._keys:
            self._refresh()
        return self._keys.get(kid)

    def _is_stale(self) -> bool:
        return (time.time() - self._fetched_at) >= self._ttl_seconds

    def _refresh(self) -> None:
        with self._lock:
            # Double-check after acquiring lock
            if not self._is_stale() and self._keys:
                return
            try:
                resp = requests.get(self._jwks_url, timeout=5)
                resp.raise_for_status()
                jwks = resp.json()
                self._keys = {k["kid"]: k for k in jwks.get("keys", [])}
                self._fetched_at = time.time()
            except Exception:
                logger.exception("Failed to fetch JWKS from %s", self._jwks_url)
                # Keep stale keys if we have them
                if not self._keys:
                    raise


class AgentCoreIdentityMiddleware:
    """Cognito JWT authentication middleware for Flask.

    Validates Bearer JWT tokens against a Cognito User Pool, resolves
    the cognito_sub to an application user (user_id, family_id, role),
    and provides ``require_auth`` / ``require_role`` decorators.
    """

    def __init__(
        self,
        cognito_user_pool_id: str,
        cognito_client_id: str,
        region: str,
    ) -> None:
        self._user_pool_id = cognito_user_pool_id
        self._client_id = cognito_client_id
        self._region = region
        self._issuer = (
            f"https://cognito-idp.{region}.amazonaws.com/{cognito_user_pool_id}"
        )
        jwks_url = f"{self._issuer}/.well-known/jwks.json"
        self._jwks_cache = _JWKSCache(jwks_url, ttl_seconds=3600)

    # ------------------------------------------------------------------
    # Token validation
    # ------------------------------------------------------------------

    def validate_token(self, token: str) -> IdentityContext:
        """Verify a JWT against the Cognito User Pool and resolve identity.

        Returns an ``IdentityContext`` with user_id, family_id, role, and
        cognito_sub populated from the Users DynamoDB table.

        Raises:
            jwt.ExpiredSignatureError: token is expired
            jwt.InvalidTokenError: token is malformed or untrusted
            LookupError: cognito_sub not found in Users table
        """
        # Decode header to get kid
        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.DecodeError as exc:
            raise jwt.InvalidTokenError("Malformed token header") from exc

        kid = unverified_header.get("kid")
        if not kid:
            raise jwt.InvalidTokenError("Token header missing 'kid'")

        # Fetch the matching public key
        jwk_data = self._jwks_cache.get_key(kid)
        if jwk_data is None:
            raise jwt.InvalidTokenError("Unknown signing key")

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk_data)

        # Verify signature, expiration, issuer, and audience
        try:
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._client_id,
                options={"require": ["exp", "iss", "sub"]},
            )
        except jwt.ExpiredSignatureError:
            raise  # Let caller handle TOKEN_EXPIRED specifically
        except jwt.InvalidTokenError:
            raise

        cognito_sub = claims["sub"]

        # Resolve application user from cognito_sub
        identity = self._resolve_user(cognito_sub)
        return identity

    def _resolve_user(self, cognito_sub: str) -> IdentityContext:
        """Look up cognito_sub in Users table via cognito_sub-index GSI."""
        dal = get_dal()
        user = dal.users.get_by_cognito_sub(cognito_sub)
        if not user:
            raise LookupError(f"User not registered for cognito_sub={cognito_sub}")
        return IdentityContext(
            user_id=user["user_id"],
            family_id=user.get("family_id"),
            role=user.get("role", "member"),
            cognito_sub=cognito_sub,
        )

    # ------------------------------------------------------------------
    # Family group resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_family_group(user_id: str, role: str) -> str | None:
        """Look up or auto-create a family group for the authenticated user.

        Queries the FamilyGroups table ``member-family-index`` GSI to find
        the user's family_id.  If no mapping exists, a new single-member
        family group is created automatically (Requirement 24.2).

        Returns the resolved ``family_id``, or ``None`` if the lookup fails
        entirely (Requirement 24.1 — proceed with member-only memory).
        """
        try:
            dal = get_dal()
            # FamilyGroups uses member-family-index GSI (member_id → family_id)
            family_table = dal.memberships._table
            result = family_table.query(
                IndexName="member-family-index",
                KeyConditionExpression="member_id = :uid",
                ExpressionAttributeValues={":uid": user_id},
                Limit=1,
            )
            items = result.get("Items", [])
            if items:
                return items[0]["family_id"]

            # No family group — auto-create a single-member family group
            family_id = f"fam_{ULID()}"
            now = datetime.now(timezone.utc).isoformat()
            family_table.put_item(
                Item={
                    "family_id": family_id,
                    "member_id": user_id,
                    "role": role,
                    "joined_at": now,
                },
            )
            logger.info(
                "Auto-created family group %s for user %s",
                family_id,
                user_id,
            )
            return family_id
        except Exception:
            logger.warning(
                "Failed to resolve family group for user %s; "
                "proceeding with member-only memory",
                user_id,
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # Decorators
    # ------------------------------------------------------------------

    def require_auth(self, f: Callable) -> Callable:
        """Decorator: extract Bearer token, validate, set Flask g context.

        Supports dual-auth mode for the migration period (Requirements 19.5,
        31.5): tries Cognito JWT validation first, then falls back to
        device-token lookup when the JWT is invalid or missing.  If the JWT
        is *expired*, 401 TOKEN_EXPIRED is returned immediately with no
        fallback — the client should refresh the token.

        Sets ``g.user_id``, ``g.family_id``, ``g.user_role``,
        ``g.cognito_sub`` on success.

        Returns 401 JSON on auth failure.
        """

        @wraps(f)
        def decorated(*args: Any, **kwargs: Any) -> Any:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return (
                    jsonify({"error": "Missing or invalid Authorization header"}),
                    401,
                )

            token = auth_header[7:]
            if not token:
                return (
                    jsonify({"error": "Missing or invalid Authorization header"}),
                    401,
                )

            # --- Try JWT validation first ---
            try:
                identity = self.validate_token(token)
            except jwt.ExpiredSignatureError:
                # Expired JWT: never fall back — client must refresh
                return (
                    jsonify({"error": "Token expired", "code": "TOKEN_EXPIRED"}),
                    401,
                )
            except LookupError:
                # Valid JWT but cognito_sub not in Users table — don't fall
                # back because the token itself was legitimate.
                return jsonify({"error": "User not registered"}), 401
            except (jwt.InvalidTokenError, Exception) as jwt_exc:
                # JWT invalid/missing/unrecognised — fall back to device-token
                logger.debug(
                    "JWT validation failed (%s), attempting device-token fallback",
                    jwt_exc,
                )
                identity = None

            if identity is not None:
                # JWT succeeded
                g.user_id = identity.user_id
                g.family_id = identity.family_id
                g.user_role = identity.role
                g.cognito_sub = identity.cognito_sub

                # Resolve family group from FamilyGroups table if not
                # already set on the identity (Requirement 24.1, 24.2).
                if not g.family_id:
                    g.family_id = self._resolve_family_group(
                        identity.user_id,
                        identity.role,
                    )

                return f(*args, **kwargs)

            # --- Device-token fallback (dual-auth migration period) ---
            return self._device_token_fallback(token, f, *args, **kwargs)

        return decorated

    # ------------------------------------------------------------------
    # Device-token fallback (migration period)
    # ------------------------------------------------------------------

    @staticmethod
    def _device_token_fallback(
        token: str, f: Callable, *args: Any, **kwargs: Any
    ) -> Any:
        """Authenticate via legacy device-token lookup.

        Mirrors the logic in ``auth.require_auth`` so that existing
        device-token clients continue to work during the migration period.
        """
        dal = get_dal()
        device = dal.devices.get_by_token(token)
        if not device:
            return jsonify({"error": "Invalid token"}), 401

        user = dal.users.get_by_id({"user_id": device["user_id"]})
        if not user:
            return jsonify({"error": "User not found"}), 401

        g.user_id = user["user_id"]
        g.user_name = user["name"]
        g.user_role = user.get("role", "member")
        g.device_id = device["device_id"]
        # Device-token auth has no Cognito fields
        g.family_id = user.get("family_id")
        g.cognito_sub = None

        # Resolve family group if not already set (Requirement 24.1, 24.2)
        if not g.family_id:
            g.family_id = AgentCoreIdentityMiddleware._resolve_family_group(
                g.user_id,
                g.user_role,
            )

        return f(*args, **kwargs)

    def require_role(self, role: str) -> Callable:
        """Decorator factory: enforce RBAC after ``require_auth``.

        Usage::

            @middleware.require_auth
            @middleware.require_role("admin")
            def admin_only_route():
                ...

        Returns 403 if the authenticated user's role does not match.
        """

        def decorator(f: Callable) -> Callable:
            @wraps(f)
            def decorated(*args: Any, **kwargs: Any) -> Any:
                user_role = g.get("user_role")
                if user_role != role:
                    return (
                        jsonify({"error": f"Forbidden: requires role '{role}'"}),
                        403,
                    )
                return f(*args, **kwargs)

            return decorated

        return decorator

    def get_identity_context(self) -> IdentityContext:
        """Return the current request's identity from Flask g."""
        return IdentityContext(
            user_id=g.user_id,
            family_id=g.get("family_id"),
            role=g.get("user_role", "member"),
            cognito_sub=g.get("cognito_sub", ""),
        )
