"""MembershipRepository — DynamoDB access for FamilyMembers table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, RepositoryConfig
from app.dal.pagination import PaginatedResult


class MembershipRepository(BaseRepository):
    """Repository for the FamilyMembers table.

    Key schema: family_id (HASH), user_id (RANGE)

    Consolidates access to family membership data. Once the Memberships
    table migration (Phase 3) is complete, this will be retargeted to
    the new table with its member-families-index GSI.
    """

    CONFIG = RepositoryConfig(
        table_name="FamilyMembers",
        partition_key="family_id",
        sort_key="user_id",
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def query_by_family(
        self, family_id: str, limit: int = 100, cursor: str | None = None
    ) -> PaginatedResult[dict[str, Any]]:
        """List all members in a family."""
        return self.query(family_id, limit=limit, cursor=cursor)

    def get_membership(self, family_id: str, user_id: str) -> dict[str, Any] | None:
        """Get a specific membership record."""
        return self.get_by_id({"family_id": family_id, "user_id": user_id})

    def delete_membership(self, family_id: str, user_id: str) -> None:
        """Remove a member from a family."""
        self.delete({"family_id": family_id, "user_id": user_id})
