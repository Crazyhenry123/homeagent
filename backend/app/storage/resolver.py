"""Request-scoped storage provider resolution."""

from __future__ import annotations

from app.storage.base import StorageProvider


def get_request_storage() -> StorageProvider | None:
    """Return the storage provider attached to the current Flask request, or None."""
    try:
        from flask import g

        return getattr(g, "storage_provider", None)
    except RuntimeError:
        return None
