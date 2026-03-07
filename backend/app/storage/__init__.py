"""Storage provider abstraction layer.

Provides the StorageProvider interface and collection constants.
Full provider implementations live in the storage-provider-abstraction branch.
"""

from app.storage.base import (
    COLLECTION_HEALTH_DOCUMENTS,
    COLLECTION_HEALTH_OBSERVATIONS,
    COLLECTION_HEALTH_RECORDS,
    StorageProvider,
)

__all__ = [
    "StorageProvider",
    "COLLECTION_HEALTH_RECORDS",
    "COLLECTION_HEALTH_OBSERVATIONS",
    "COLLECTION_HEALTH_DOCUMENTS",
]
