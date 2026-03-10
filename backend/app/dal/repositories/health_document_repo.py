"""HealthDocumentRepository — DynamoDB access for HealthDocuments table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, RepositoryConfig
from app.dal.pagination import PaginatedResult


class HealthDocumentRepository(BaseRepository):
    """Repository for the HealthDocuments table.

    Key schema: user_id (HASH), document_id (RANGE)
    """

    CONFIG = RepositoryConfig(
        table_name="HealthDocuments",
        partition_key="user_id",
        sort_key="document_id",
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def query_by_user(
        self, user_id: str, limit: int = 50, cursor: str | None = None
    ) -> PaginatedResult[dict[str, Any]]:
        """List all documents for a user."""
        return self.query(user_id, limit=limit, cursor=cursor)

    def get_document(self, user_id: str, document_id: str) -> dict[str, Any] | None:
        """Get a specific document."""
        return self.get_by_id({"user_id": user_id, "document_id": document_id})
