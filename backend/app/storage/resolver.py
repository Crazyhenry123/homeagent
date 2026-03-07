"""Resolve storage provider for the current request context."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.storage.base import StorageProvider

logger = logging.getLogger(__name__)


def get_request_storage() -> StorageProvider | None:
    """Get storage provider from Flask g context, or None if not available.

    Returns None when:
    - Not in a Flask request context (e.g., background thread)
    - No storage provider has been resolved for this request
    - User is on the default local provider
    """
    try:
        from flask import g

        return getattr(g, "storage_provider", None)
    except RuntimeError:
        return None
