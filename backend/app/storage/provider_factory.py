"""Factory for obtaining the correct StorageProvider for a given user."""

from __future__ import annotations

import logging
from typing import Any

import boto3

from app.storage.base import StorageProvider

logger = logging.getLogger(__name__)

# Provider name → import path (lazy-loaded)
_PROVIDER_MAP: dict[str, tuple[str, str]] = {
    "local": ("app.storage.local_provider", "LocalProvider"),
    "google_drive": ("app.storage.google_drive_provider", "GoogleDriveProvider"),
    "onedrive": ("app.storage.onedrive_provider", "OneDriveProvider"),
    "dropbox": ("app.storage.dropbox_provider", "DropboxProvider"),
    "box": ("app.storage.box_provider", "BoxProvider"),
}


def _get_storage_config_table() -> Any:
    """Return the StorageConfig DynamoDB table resource."""
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
        return g.dynamodb.Table("StorageConfig")
    except RuntimeError:
        dynamodb = boto3.resource("dynamodb")
        return dynamodb.Table("StorageConfig")


def _load_provider_class(provider_name: str) -> type[StorageProvider]:
    """Dynamically import and return the provider class."""
    import importlib

    module_path, class_name = _PROVIDER_MAP[provider_name]
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def get_storage_provider(user_id: str) -> StorageProvider:
    """Return the configured :class:`StorageProvider` for *user_id*.

    Reads the ``StorageConfig`` DynamoDB table to determine which provider the
    user has configured.  Falls back to the local (DynamoDB + S3) provider when
    no configuration exists or on any error.
    """
    provider_name = "local"

    try:
        # Check if storage providers feature is enabled
        try:
            from flask import current_app  # noqa: WPS433

            enabled = current_app.config.get("STORAGE_PROVIDERS_ENABLED", False)
        except RuntimeError:
            import os

            enabled = os.environ.get(
                "STORAGE_PROVIDERS_ENABLED", "false"
            ).lower() == "true"

        if enabled:
            table = _get_storage_config_table()
            response = table.get_item(Key={"user_id": user_id})
            item = response.get("Item")
            if item:
                configured = item.get("provider", "local")
                if configured in _PROVIDER_MAP:
                    provider_name = configured
                else:
                    logger.warning(
                        "Unknown storage provider '%s' for user=%s, falling back to local",
                        configured,
                        user_id,
                    )
    except Exception:
        logger.exception(
            "Failed to read storage config for user=%s, using local provider",
            user_id,
        )

    cls = _load_provider_class(provider_name)
    return cls(user_id)
