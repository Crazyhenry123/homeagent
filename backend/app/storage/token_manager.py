"""OAuth token management for cloud storage providers."""

from __future__ import annotations

import logging
import time
from typing import Any

import boto3
import requests

logger = logging.getLogger(__name__)

# Provider-specific token refresh endpoints
_REFRESH_ENDPOINTS: dict[str, str] = {
    "google_drive": "https://oauth2.googleapis.com/token",
    "onedrive": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    "dropbox": "https://api.dropboxapi.com/oauth2/token",
    "box": "https://api.box.com/oauth2/token",
}


class OAuthTokenManager:
    """Read / write / refresh OAuth tokens stored in the OAuthTokens DynamoDB table."""

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_table(self) -> Any:
        """Return the OAuthTokens DynamoDB Table resource."""
        try:
            from flask import current_app, g  # noqa: WPS433

            if "dynamodb" not in g:
                endpoint_url = current_app.config.get("DYNAMODB_ENDPOINT")
                kwargs: dict[str, Any] = {
                    "region_name": current_app.config["AWS_REGION"]
                }
                if endpoint_url:
                    kwargs["endpoint_url"] = endpoint_url
                g.dynamodb = boto3.resource("dynamodb", **kwargs)
            return g.dynamodb.Table("OAuthTokens")
        except RuntimeError:
            dynamodb = boto3.resource("dynamodb")
            return dynamodb.Table("OAuthTokens")

    def _get_config(self, provider: str) -> dict[str, str]:
        """Return OAuth client_id / client_secret for *provider*."""
        try:
            from flask import current_app  # noqa: WPS433

            prefix = provider.upper()
            return {
                "client_id": current_app.config.get(f"{prefix}_CLIENT_ID", ""),
                "client_secret": current_app.config.get(
                    f"{prefix}_CLIENT_SECRET", ""
                ),
            }
        except RuntimeError:
            import os

            prefix = provider.upper()
            return {
                "client_id": os.environ.get(f"{prefix}_CLIENT_ID", ""),
                "client_secret": os.environ.get(f"{prefix}_CLIENT_SECRET", ""),
            }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_valid_token(self, provider: str) -> str | None:
        """Return a valid access token, refreshing if necessary.

        Returns ``None`` if no token is stored or refresh fails.
        """
        try:
            table = self._get_table()
            response = table.get_item(
                Key={"user_id": self._user_id, "provider": provider}
            )
            item = response.get("Item")
            if not item:
                return None

            # Check expiry (with 5-minute buffer)
            expires_at = item.get("expires_at", 0)
            if time.time() < (float(expires_at) - 300):
                return item.get("access_token")

            # Token expired or about to expire – try refresh
            refresh_token = item.get("refresh_token")
            if not refresh_token:
                logger.warning(
                    "No refresh token for user=%s provider=%s",
                    self._user_id,
                    provider,
                )
                return None

            return self._refresh_token(provider, refresh_token)
        except Exception:
            logger.exception(
                "get_valid_token failed for user=%s provider=%s",
                self._user_id,
                provider,
            )
            return None

    def store_tokens(
        self,
        provider: str,
        access_token: str,
        refresh_token: str | None = None,
        expires_in: int = 3600,
    ) -> bool:
        """Persist OAuth tokens to DynamoDB."""
        try:
            table = self._get_table()
            item: dict[str, Any] = {
                "user_id": self._user_id,
                "provider": provider,
                "access_token": access_token,
                "expires_at": int(time.time() + expires_in),
            }
            if refresh_token:
                item["refresh_token"] = refresh_token
            table.put_item(Item=item)
            return True
        except Exception:
            logger.exception(
                "store_tokens failed for user=%s provider=%s",
                self._user_id,
                provider,
            )
            return False

    def delete_tokens(self, provider: str) -> bool:
        """Remove stored tokens for a provider."""
        try:
            table = self._get_table()
            table.delete_item(
                Key={"user_id": self._user_id, "provider": provider}
            )
            return True
        except Exception:
            logger.exception(
                "delete_tokens failed for user=%s provider=%s",
                self._user_id,
                provider,
            )
            return False

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    def _refresh_token(self, provider: str, refresh_token: str) -> str | None:
        """Exchange a refresh token for a new access token.

        On success the new tokens are persisted and the access token returned.
        Returns ``None`` on failure.
        """
        endpoint = _REFRESH_ENDPOINTS.get(provider)
        if not endpoint:
            logger.error("No refresh endpoint for provider=%s", provider)
            return None

        config = self._get_config(provider)

        payload: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
        }

        try:
            resp = requests.post(endpoint, data=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            new_access = data["access_token"]
            new_refresh = data.get("refresh_token", refresh_token)
            expires_in = int(data.get("expires_in", 3600))

            self.store_tokens(
                provider,
                access_token=new_access,
                refresh_token=new_refresh,
                expires_in=expires_in,
            )
            return new_access
        except Exception:
            logger.exception(
                "Token refresh failed for user=%s provider=%s",
                self._user_id,
                provider,
            )
            return None
