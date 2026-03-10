"""DeviceRepository — DynamoDB access for Devices table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, GSIConfig, RepositoryConfig
from app.dal.pagination import PaginatedResult


class DeviceRepository(BaseRepository):
    """Repository for the Devices table.

    Key schema: device_id (HASH)
    GSIs: device_token-index, user_id-index
    """

    CONFIG = RepositoryConfig(
        table_name="Devices",
        partition_key="device_id",
        gsi_definitions=[
            GSIConfig(index_name="device_token-index", partition_key="device_token"),
            GSIConfig(index_name="user_id-index", partition_key="user_id"),
        ],
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def get_by_token(self, device_token: str) -> dict[str, Any] | None:
        """Look up a device by its token via device_token-index GSI."""
        result = self.query(device_token, index_name="device_token-index", limit=1)
        return result.items[0] if result.items else None

    def query_by_user(
        self, user_id: str, limit: int = 20, cursor: str | None = None
    ) -> PaginatedResult[dict[str, Any]]:
        """List all devices for a user via user_id-index GSI."""
        return self.query(
            user_id, index_name="user_id-index", limit=limit, cursor=cursor
        )
