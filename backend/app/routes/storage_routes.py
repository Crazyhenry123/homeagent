"""API routes for user storage provider configuration and OAuth callbacks."""

from __future__ import annotations

import logging
import secrets
import time
from typing import Any
from urllib.parse import quote, urlencode

from flask import Blueprint, current_app, g, jsonify, redirect, request

from app.auth import require_admin, require_auth
from app.models.dynamo import get_table

logger = logging.getLogger(__name__)

storage_bp = Blueprint("storage", __name__)


def _get_oauth_credentials(provider_id: str) -> tuple[str, str]:
    """Get OAuth client_id and client_secret for a provider.

    Checks DynamoDB (admin-configured) first, falls back to env vars.
    Returns (client_id, client_secret) — both empty strings if not configured.
    """
    try:
        table = get_table("OAuthAppCredentials")
        result = table.get_item(Key={"provider": provider_id})
        item = result.get("Item")
        if item and item.get("client_id"):
            return item["client_id"], item.get("client_secret", "")
    except Exception:
        logger.debug("Failed to read OAuthAppCredentials for %s", provider_id)

    prefix = provider_id.upper()
    client_id = current_app.config.get(f"{prefix}_CLIENT_ID", "")
    client_secret = current_app.config.get(f"{prefix}_CLIENT_SECRET", "")
    return client_id, client_secret

# Supported providers with metadata
PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "local",
        "name": "Default (Secure Cloud)",
        "description": "Data stored in HomeAgent's encrypted cloud infrastructure",
        "requires_oauth": False,
    },
    {
        "id": "google_drive",
        "name": "Google Drive",
        "description": "Store personal data in your Google Drive account",
        "requires_oauth": True,
    },
    {
        "id": "onedrive",
        "name": "OneDrive",
        "description": "Store personal data in your Microsoft OneDrive",
        "requires_oauth": True,
    },
    {
        "id": "dropbox",
        "name": "Dropbox",
        "description": "Store personal data in your Dropbox account",
        "requires_oauth": True,
    },
    {
        "id": "box",
        "name": "Box",
        "description": "Store personal data in your Box account",
        "requires_oauth": True,
    },
]

VALID_PROVIDER_IDS = {p["id"] for p in PROVIDERS}

# OAuth authorization URLs and scopes
_OAUTH_CONFIGS: dict[str, dict[str, str]] = {
    "google_drive": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/drive.file",
    },
    "onedrive": {
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "Files.ReadWrite.All offline_access",
    },
    "dropbox": {
        "auth_url": "https://www.dropbox.com/oauth2/authorize",
        "token_url": "https://api.dropboxapi.com/oauth2/token",
        "scope": "",
    },
    "box": {
        "auth_url": "https://account.box.com/api/oauth2/authorize",
        "token_url": "https://api.box.com/oauth2/token",
        "scope": "",
    },
}


# ── Provider listing ──────────────────────────────────────────────


@storage_bp.route("/storage/providers", methods=["GET"])
@require_auth
def list_providers():
    """Return available storage providers with current user's active provider."""
    from app.services.storage_config import get_storage_config

    config = get_storage_config(g.user_id)
    current = config.get("provider", "local") if config else "local"
    status = config.get("status", "active") if config else "active"

    # Enrich providers with oauth_configured status
    is_admin = g.get("user_role") in ("admin", "owner")
    enriched: list[dict[str, Any]] = []
    for p in PROVIDERS:
        provider = dict(p)
        if p["requires_oauth"]:
            client_id, _ = _get_oauth_credentials(p["id"])
            provider["oauth_configured"] = bool(client_id)
        else:
            provider["oauth_configured"] = True
        enriched.append(provider)

    return jsonify({
        "providers": enriched,
        "current_provider": current,
        "current_status": status,
    })


# ── Connect / disconnect ─────────────────────────────────────────


@storage_bp.route("/storage/connect/<provider_id>", methods=["POST"])
@require_auth
def connect_provider(provider_id: str):
    """Start the OAuth flow for a cloud storage provider.

    Returns an authorization URL that the client should open in a browser.
    """
    if provider_id not in VALID_PROVIDER_IDS or provider_id == "local":
        return jsonify({"error": "Invalid provider"}), 400

    oauth_cfg = _OAUTH_CONFIGS.get(provider_id)
    if not oauth_cfg:
        return jsonify({"error": "Provider not configured"}), 400

    client_id, _ = _get_oauth_credentials(provider_id)
    if not client_id:
        return jsonify({"error": f"{provider_id} OAuth not configured on server"}), 400

    # Generate CSRF state token
    state = secrets.token_urlsafe(32)
    state_table = get_table("OAuthState")
    state_table.put_item(Item={
        "state": state,
        "user_id": g.user_id,
        "provider": provider_id,
        "expires_at": int(time.time()) + 600,  # 10 min TTL
    })

    redirect_uri = request.json.get("redirect_uri", "") if request.is_json else ""
    if not redirect_uri:
        redirect_uri = request.host_url.rstrip("/") + f"/api/storage/oauth/callback/{provider_id}"
    else:
        # Validate redirect_uri is on our own host to prevent open redirects
        from urllib.parse import urlparse

        parsed = urlparse(redirect_uri)
        expected_host = urlparse(request.host_url).hostname
        if parsed.hostname != expected_host:
            return jsonify({"error": "Invalid redirect_uri"}), 400

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    if oauth_cfg["scope"]:
        params["scope"] = oauth_cfg["scope"]

    auth_url = oauth_cfg["auth_url"] + "?" + urlencode(params)

    return jsonify({"auth_url": auth_url, "state": state})


@storage_bp.route("/storage/disconnect", methods=["POST"])
@require_auth
def disconnect_provider():
    """Disconnect the current cloud storage provider (revert to local)."""
    from app.services.storage_config import clear_storage_config
    from app.storage.token_manager import OAuthTokenManager

    from app.services.storage_config import get_storage_config

    config = get_storage_config(g.user_id)
    if config and config.get("provider", "local") != "local":
        provider = config["provider"]
        token_mgr = OAuthTokenManager(g.user_id)
        token_mgr.delete_tokens(provider)

    clear_storage_config(g.user_id)
    return jsonify({"success": True, "provider": "local"})


# ── OAuth callbacks ───────────────────────────────────────────────


@storage_bp.route("/storage/oauth/callback/<provider_id>", methods=["GET"])
def oauth_callback(provider_id: str):
    """Handle OAuth redirect from cloud provider.

    Exchanges the authorization code for tokens and stores them.
    Redirects to a deep link for mobile or returns JSON for web.
    """
    import requests as http_requests

    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    if error:
        return _callback_response(False, f"OAuth error: {error}")
    if not code or not state:
        return _callback_response(False, "Missing code or state")

    # Validate and atomically consume state token (CSRF)
    state_table = get_table("OAuthState")
    try:
        resp = state_table.delete_item(
            Key={"state": state},
            ConditionExpression="attribute_exists(#s)",
            ExpressionAttributeNames={"#s": "state"},
            ReturnValues="ALL_OLD",
        )
        state_item = resp.get("Attributes")
    except state_table.meta.client.exceptions.ConditionalCheckFailedException:
        state_item = None

    if not state_item:
        return _callback_response(False, "Invalid or expired state")

    # Check TTL expiry
    if int(state_item.get("expires_at", 0)) < int(time.time()):
        return _callback_response(False, "State token expired")

    if state_item.get("provider") != provider_id:
        return _callback_response(False, "Provider mismatch")

    user_id = state_item["user_id"]

    # Exchange code for tokens
    oauth_cfg = _OAUTH_CONFIGS.get(provider_id)
    if not oauth_cfg:
        return _callback_response(False, "Unknown provider")

    client_id, client_secret = _get_oauth_credentials(provider_id)

    redirect_uri = request.base_url  # Same URL that received the callback

    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    try:
        resp = http_requests.post(
            oauth_cfg["token_url"], data=token_payload, timeout=30
        )
        resp.raise_for_status()
        token_data = resp.json()
    except Exception:
        logger.exception("OAuth token exchange failed for %s", provider_id)
        return _callback_response(False, "Token exchange failed")

    # Store tokens
    from app.storage.token_manager import OAuthTokenManager

    token_mgr = OAuthTokenManager(user_id)
    token_mgr.store_tokens(
        provider=provider_id,
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        expires_in=int(token_data.get("expires_in", 3600)),
    )

    # Update storage config
    from app.services.storage_config import set_storage_config

    set_storage_config(user_id, provider_id, status="active")

    return _callback_response(True)


def _callback_response(success: bool, message: str = "") -> Any:
    """Return either a deep-link redirect (mobile) or JSON (web)."""
    status = "success" if success else "error"
    deep_link = f"homeagent://storage-connected?status={status}"
    if message:
        deep_link += f"&message={quote(message)}"

    # If the request looks like a browser (Accept: text/html), redirect
    accept = request.headers.get("Accept", "")
    if "text/html" in accept:
        return redirect(deep_link)

    if success:
        return jsonify({"success": True})
    return jsonify({"error": message}), 400


# ── Health check / test ───────────────────────────────────────────


@storage_bp.route("/storage/test", methods=["POST"])
@require_auth
def test_connection():
    """Test the current storage provider connection."""
    import time as time_mod

    from app.storage.provider_factory import get_storage_provider

    start = time_mod.time()
    try:
        provider = get_storage_provider(g.user_id)
        result = provider.health_check()
        latency_ms = int((time_mod.time() - start) * 1000)
        return jsonify({
            "reachable": result.get("ok", False),
            "latency_ms": latency_ms,
            "provider": result.get("provider", "unknown"),
        })
    except Exception:
        latency_ms = int((time_mod.time() - start) * 1000)
        return jsonify({"reachable": False, "latency_ms": latency_ms})


# ── Admin: OAuth app credential management ────────────────────────


@storage_bp.route("/storage/admin/credentials", methods=["GET"])
@require_auth
@require_admin
def list_credentials():
    """List configured OAuth app credentials (client_id only, no secrets)."""
    result: dict[str, dict[str, str]] = {}
    for provider_id in ("google_drive", "onedrive", "dropbox", "box"):
        client_id, _ = _get_oauth_credentials(provider_id)
        if client_id:
            # Mask all but last 4 chars
            masked = "****" + client_id[-4:] if len(client_id) > 4 else "****"
            result[provider_id] = {"client_id": masked, "configured": True}
        else:
            result[provider_id] = {"client_id": "", "configured": False}
    return jsonify(result)


@storage_bp.route("/storage/admin/credentials/<provider_id>", methods=["PUT"])
@require_auth
@require_admin
def save_credentials(provider_id: str):
    """Save OAuth app credentials for a provider (admin only)."""
    if provider_id not in VALID_PROVIDER_IDS or provider_id == "local":
        return jsonify({"error": "Invalid provider"}), 400

    if not request.is_json:
        return jsonify({"error": "JSON body required"}), 400

    client_id = (request.json.get("client_id") or "").strip()
    client_secret = (request.json.get("client_secret") or "").strip()

    if not client_id or not client_secret:
        return jsonify({"error": "Both client_id and client_secret are required"}), 400

    table = get_table("OAuthAppCredentials")
    table.put_item(Item={
        "provider": provider_id,
        "client_id": client_id,
        "client_secret": client_secret,
        "configured_by": g.user_id,
        "configured_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    })

    logger.info(
        "Admin %s configured OAuth credentials for %s", g.user_id, provider_id
    )
    return jsonify({"success": True, "provider": provider_id})


@storage_bp.route("/storage/admin/credentials/<provider_id>", methods=["DELETE"])
@require_auth
@require_admin
def delete_credentials(provider_id: str):
    """Remove OAuth app credentials for a provider (admin only)."""
    if provider_id not in VALID_PROVIDER_IDS or provider_id == "local":
        return jsonify({"error": "Invalid provider"}), 400

    table = get_table("OAuthAppCredentials")
    table.delete_item(Key={"provider": provider_id})

    logger.info(
        "Admin %s removed OAuth credentials for %s", g.user_id, provider_id
    )
    return jsonify({"success": True, "provider": provider_id})
