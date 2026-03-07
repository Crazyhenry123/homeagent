import logging
from functools import wraps
from typing import Callable

from flask import g, jsonify, request

from app.models.dynamo import get_table

logger = logging.getLogger(__name__)


def _try_cognito_auth(token: str) -> bool:
    """Attempt to authenticate with a Cognito JWT.

    Returns True and populates Flask g if successful, False otherwise.
    """
    try:
        from app.services.cognito import CognitoError, verify_token
        from app.services.user import get_user_by_cognito_sub

        claims = verify_token(token)
        cognito_sub = claims.get("sub")
        if not cognito_sub:
            return False

        user = get_user_by_cognito_sub(cognito_sub)
        if not user:
            return False

        g.user_id = user["user_id"]
        g.user_name = user["name"]
        g.user_role = user.get("role", "member")
        g.cognito_sub = cognito_sub
        return True
    except ImportError:
        return False
    except Exception:
        logger.warning("Cognito auth error: %s", token[:10], exc_info=True)
        return False


def _try_device_auth(token: str) -> bool:
    """Attempt to authenticate with a device token.

    Returns True and populates Flask g if successful, False otherwise.
    """
    try:
        devices_table = get_table("Devices")
        result = devices_table.query(
            IndexName="device_token-index",
            KeyConditionExpression="device_token = :token",
            ExpressionAttributeValues={":token": token},
            Limit=1,
        )

        items = result.get("Items", [])
        if not items:
            return False

        device = items[0]

        users_table = get_table("Users")
        user = users_table.get_item(Key={"user_id": device["user_id"]}).get("Item")
        if not user:
            return False

        g.user_id = user["user_id"]
        g.user_name = user["name"]
        g.user_role = user.get("role", "member")
        g.device_id = device["device_id"]
        return True
    except Exception:
        logger.warning("Device auth error", exc_info=True)
        return False


def _resolve_storage_provider() -> None:
    """Resolve the storage provider for the authenticated user on Flask g.

    Sets g.storage_provider to the user's configured provider, or None
    for the default local provider. Failures are silently ignored.
    """
    try:
        from app.services.storage_config import get_storage_config

        config = get_storage_config(g.user_id)
        if config and config.get("provider", "local") != "local":
            from app.storage.provider_factory import get_storage_provider

            g.storage_provider = get_storage_provider(g.user_id)
        else:
            g.storage_provider = None
    except (ImportError, Exception):
        g.storage_provider = None


def require_auth(f: Callable) -> Callable:
    """Middleware that validates auth token (Cognito JWT or device token)."""

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header[7:]
        if not token:
            return jsonify({"error": "Empty token"}), 401

        # Try Cognito JWT first, then fall back to device token
        if not _try_cognito_auth(token) and not _try_device_auth(token):
            return jsonify({"error": "Invalid token"}), 401

        # Resolve storage provider for this user
        _resolve_storage_provider()

        return f(*args, **kwargs)

    return decorated


def require_cognito_auth(f: Callable) -> Callable:
    """Middleware that validates a Cognito access_token from Authorization header.

    Attaches user info to Flask g context.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        from app.services.cognito import CognitoError, verify_token
        from app.services.user import get_user_by_cognito_sub

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header[7:]
        if not token:
            return jsonify({"error": "Empty token"}), 401

        try:
            claims = verify_token(token)
        except CognitoError as e:
            logger.debug("Cognito token verification failed: %s", e)
            return jsonify({"error": str(e)}), 401

        cognito_sub = claims.get("sub")
        if not cognito_sub:
            return jsonify({"error": "Token missing sub claim"}), 401

        user = get_user_by_cognito_sub(cognito_sub)
        if not user:
            return jsonify({"error": "User not found"}), 401

        g.user_id = user["user_id"]
        g.user_name = user["name"]
        g.user_role = user.get("role", "member")
        g.cognito_sub = cognito_sub

        return f(*args, **kwargs)

    return decorated


def require_admin(f: Callable) -> Callable:
    """Middleware that requires admin role. Must be used after require_auth."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if g.get("user_role") not in ("admin", "owner"):
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)

    return decorated


def require_owner(f: Callable) -> Callable:
    """Middleware that requires owner role.

    Must be used after require_auth or require_cognito_auth.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        if g.get("user_role") != "owner":
            return jsonify({"error": "Owner access required"}), 403
        return f(*args, **kwargs)

    return decorated
