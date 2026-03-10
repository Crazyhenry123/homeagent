"""HealthRecordRepository — DynamoDB access for HealthRecords table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, GSIConfig, RepositoryConfig
from app.dal.pagination import PaginatedResult


class HealthRecordRepository(BaseRepository):
    """Repository for the HealthRecords table.

    Key schema: user_id (HASH), record_id (RANGE)
    GSIs: record_type-index (PK: user_id, SK: record_type)
    """

    CONFIG = RepositoryConfig(
        table_name="HealthRecords",
        partition_key="user_id",
        sort_key="record_id",
        gsi_definitions=[
            GSIConfig(
                index_name="record_type-index",
                partition_key="user_id",
                sort_key="record_type",
            ),
        ],
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def query_by_user(
        self, user_id: str, limit: int = 50, cursor: str | None = None
    ) -> PaginatedResult[dict[str, Any]]:
        """List all health records for a user."""
        return self.query(user_id, limit=limit, cursor=cursor)

    def query_by_record_type(
        self,
        user_id: str,
        record_type: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> PaginatedResult[dict[str, Any]]:
        """List health records filtered by type via record_type-index."""
        from boto3.dynamodb.conditions import Key

        return self.query(
            user_id,
            sort_condition=Key("record_type").eq(record_type),
            index_name="record_type-index",
            limit=limit,
            cursor=cursor,
        )

    def get_record(self, user_id: str, record_id: str) -> dict[str, Any] | None:
        """Get a specific health record."""
        return self.get_by_id({"user_id": user_id, "record_id": record_id})
