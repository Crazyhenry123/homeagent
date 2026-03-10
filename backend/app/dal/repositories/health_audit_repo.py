"""HealthAuditRepository — DynamoDB access for HealthAuditLog table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, GSIConfig, RepositoryConfig
from app.dal.pagination import PaginatedResult


class HealthAuditRepository(BaseRepository):
    """Repository for the HealthAuditLog table.

    Key schema: record_id (HASH), audit_sk (RANGE)
    GSIs: user-audit-index (PK: user_id, SK: created_at)
    """

    CONFIG = RepositoryConfig(
        table_name="HealthAuditLog",
        partition_key="record_id",
        sort_key="audit_sk",
        gsi_definitions=[
            GSIConfig(
                index_name="user-audit-index",
                partition_key="user_id",
                sort_key="created_at",
            ),
        ],
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def query_by_record(
        self, record_id: str, limit: int = 50, cursor: str | None = None
    ) -> PaginatedResult[dict[str, Any]]:
        """List all audit entries for a health record."""
        return self.query(record_id, limit=limit, cursor=cursor)

    def query_by_user(
        self,
        user_id: str,
        limit: int = 50,
        cursor: str | None = None,
        newest_first: bool = True,
    ) -> PaginatedResult[dict[str, Any]]:
        """List audit entries for a user via user-audit-index, newest first."""
        return self.query(
            user_id,
            index_name="user-audit-index",
            limit=limit,
            cursor=cursor,
            scan_forward=not newest_first,
        )
