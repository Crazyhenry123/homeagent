"""UserRepository — DynamoDB access for Users table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, GSIConfig, RepositoryConfig
from app.dal.pagination import PaginatedResult


class UserRepository(BaseRepository):
    """Repository for the Users table.

    Key schema: user_id (HASH)
    GSIs: email-index, cognito_sub-index
    """

    CONFIG = RepositoryConfig(
        table_name="Users",
        partition_key="user_id",
        gsi_definitions=[
            GSIConfig(index_name="email-index", partition_key="email"),
            GSIConfig(index_name="cognito_sub-index", partition_key="cognito_sub"),
        ],
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        """Get a user by user_id."""
        return self.get_by_id({"user_id": user_id})

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        """Look up a user by email via email-index GSI."""
        result = self.query(email, index_name="email-index", limit=1)
        return result.items[0] if result.items else None

    def get_by_cognito_sub(self, cognito_sub: str) -> dict[str, Any] | None:
        """Look up a user by Cognito sub via cognito_sub-index GSI."""
        result = self.query(cognito_sub, index_name="cognito_sub-index", limit=1)
        return result.items[0] if result.items else None

    def list_all(self, limit: int = 100) -> PaginatedResult[dict[str, Any]]:
        """Scan all users (admin use only). Capped to limit."""
        result = self._table.scan(Limit=limit)
        items = result.get("Items", [])
        return PaginatedResult(items=items, next_cursor=None, count=len(items))
