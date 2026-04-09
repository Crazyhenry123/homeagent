"""MemorySharingConfigRepository — DynamoDB access for MemorySharingConfig table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, RepositoryConfig


class MemorySharingConfigRepository(BaseRepository):
    """Repository for the MemorySharingConfig table.

    Key schema: user_id (HASH)
    """

    CONFIG = RepositoryConfig(
        table_name="MemorySharingConfig",
        partition_key="user_id",
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def get_config(self, user_id: str) -> dict[str, Any] | None:
        """Get memory sharing config for a user."""
        return self.get_by_id({"user_id": user_id})
