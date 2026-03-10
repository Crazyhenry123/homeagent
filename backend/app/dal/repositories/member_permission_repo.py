"""MemberPermissionRepository — DynamoDB access for MemberPermissions table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, RepositoryConfig
from app.dal.pagination import PaginatedResult


class MemberPermissionRepository(BaseRepository):
    """Repository for the MemberPermissions table.

    Key schema: user_id (HASH), permission_type (RANGE)
    """

    CONFIG = RepositoryConfig(
        table_name="MemberPermissions",
        partition_key="user_id",
        sort_key="permission_type",
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def query_by_user(
        self, user_id: str, limit: int = 50, cursor: str | None = None
    ) -> PaginatedResult[dict[str, Any]]:
        """List all permissions for a user."""
        return self.query(user_id, limit=limit, cursor=cursor)

    def get_permission(
        self, user_id: str, permission_type: str
    ) -> dict[str, Any] | None:
        """Get a specific permission."""
        return self.get_by_id({"user_id": user_id, "permission_type": permission_type})

    def delete_permission(self, user_id: str, permission_type: str) -> None:
        """Delete a specific permission."""
        self.delete({"user_id": user_id, "permission_type": permission_type})
