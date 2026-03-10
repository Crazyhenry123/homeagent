"""OAuthTokenRepository — DynamoDB access for OAuthTokens table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, RepositoryConfig
from app.dal.pagination import PaginatedResult


class OAuthTokenRepository(BaseRepository):
    """Repository for the OAuthTokens table.

    Key schema: user_id (HASH), provider (RANGE)
    """

    CONFIG = RepositoryConfig(
        table_name="OAuthTokens",
        partition_key="user_id",
        sort_key="provider",
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def query_by_user(
        self, user_id: str, limit: int = 20, cursor: str | None = None
    ) -> PaginatedResult[dict[str, Any]]:
        """List all OAuth tokens for a user."""
        return self.query(user_id, limit=limit, cursor=cursor)

    def get_token(self, user_id: str, provider: str) -> dict[str, Any] | None:
        """Get a specific OAuth token."""
        return self.get_by_id({"user_id": user_id, "provider": provider})

    def delete_token(self, user_id: str, provider: str) -> None:
        """Delete a specific OAuth token."""
        self.delete({"user_id": user_id, "provider": provider})
