"""FamilyRelationshipRepository — DynamoDB access for FamilyRelationships table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, RepositoryConfig
from app.dal.pagination import PaginatedResult


class FamilyRelationshipRepository(BaseRepository):
    """Repository for the FamilyRelationships table.

    Key schema: user_id (HASH), related_user_id (RANGE)
    """

    CONFIG = RepositoryConfig(
        table_name="FamilyRelationships",
        partition_key="user_id",
        sort_key="related_user_id",
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def query_by_user(
        self, user_id: str, limit: int = 100, cursor: str | None = None
    ) -> PaginatedResult[dict[str, Any]]:
        """List all relationships for a user."""
        return self.query(user_id, limit=limit, cursor=cursor)

    def get_relationship(
        self, user_id: str, related_user_id: str
    ) -> dict[str, Any] | None:
        """Get a specific relationship."""
        return self.get_by_id({"user_id": user_id, "related_user_id": related_user_id})

    def delete_relationship(self, user_id: str, related_user_id: str) -> None:
        """Delete a specific relationship."""
        self.delete({"user_id": user_id, "related_user_id": related_user_id})
