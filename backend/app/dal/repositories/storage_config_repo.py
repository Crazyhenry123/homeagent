"""StorageConfigRepository — DynamoDB access for StorageConfig table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, RepositoryConfig


class StorageConfigRepository(BaseRepository):
    """Repository for the StorageConfig table.

    Key schema: user_id (HASH)
    """

    CONFIG = RepositoryConfig(
        table_name="StorageConfig",
        partition_key="user_id",
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)
