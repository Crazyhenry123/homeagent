"""InviteCodeRepository — DynamoDB access for InviteCodes table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, GSIConfig, RepositoryConfig
from app.dal.pagination import PaginatedResult


class InviteCodeRepository(BaseRepository):
    """Repository for the InviteCodes table.

    Key schema: code (HASH)
    GSIs: invited_email-index
    """

    CONFIG = RepositoryConfig(
        table_name="InviteCodes",
        partition_key="code",
        gsi_definitions=[
            GSIConfig(index_name="invited_email-index", partition_key="invited_email"),
        ],
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        """Look up an invite code by invited email."""
        result = self.query(email, index_name="invited_email-index", limit=1)
        return result.items[0] if result.items else None

    def query_by_email(
        self, email: str, limit: int = 20, cursor: str | None = None
    ) -> PaginatedResult[dict[str, Any]]:
        """List all invite codes for an email."""
        return self.query(
            email, index_name="invited_email-index", limit=limit, cursor=cursor
        )
