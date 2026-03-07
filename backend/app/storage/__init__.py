"""User storage provider abstraction layer."""

from app.storage.base import (
    COLLECTION_HEALTH_DOCUMENTS,
    COLLECTION_HEALTH_OBSERVATIONS,
    COLLECTION_HEALTH_RECORDS,
    StorageProvider,
)
from app.storage.provider_factory import get_storage_provider

__all__ = [
    "StorageProvider",
    "get_storage_provider",
    "COLLECTION_HEALTH_RECORDS",
    "COLLECTION_HEALTH_OBSERVATIONS",
    "COLLECTION_HEALTH_DOCUMENTS",
]
