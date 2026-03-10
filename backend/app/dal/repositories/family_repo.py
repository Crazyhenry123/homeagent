"""FamilyRepository — DynamoDB access for Families table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, GSIConfig, RepositoryConfig
from app.dal.pagination import PaginatedResult


class FamilyRepository(BaseRepository):
    """Repository for the Families table.

    Key schema: family_id (HASH)
    GSIs: owner-index
    """

    CONFIG = RepositoryConfig(
        table_name="Families",
        partition_key="family_id",
        gsi_definitions=[
            GSIConfig(index_name="owner-index", partition_key="owner_user_id"),
        ],
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def get_by_owner(self, owner_user_id: str) -> dict[str, Any] | None:
        """Look up a family by owner user ID via owner-index GSI."""
        result = self.query(owner_user_id, index_name="owner-index", limit=1)
        return result.items[0] if result.items else None

    def query_by_owner(
        self, owner_user_id: str, limit: int = 20, cursor: str | None = None
    ) -> PaginatedResult[dict[str, Any]]:
        """List all families owned by a user."""
        return self.query(
            owner_user_id, index_name="owner-index", limit=limit, cursor=cursor
        )
