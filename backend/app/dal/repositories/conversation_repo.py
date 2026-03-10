"""ConversationRepository — DynamoDB access for Conversations table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, GSIConfig, RepositoryConfig
from app.dal.pagination import PaginatedResult


class ConversationRepository(BaseRepository):
    """Repository for the Conversations table.

    Key schema: conversation_id (HASH)
    GSIs: user_conversations-index (PK: user_id, SK: updated_at)
    """

    CONFIG = RepositoryConfig(
        table_name="Conversations",
        partition_key="conversation_id",
        gsi_definitions=[
            GSIConfig(
                index_name="user_conversations-index",
                partition_key="user_id",
                sort_key="updated_at",
            ),
        ],
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        """Get a conversation by ID."""
        return self.get_by_id({"conversation_id": conversation_id})

    def query_by_user(
        self,
        user_id: str,
        limit: int = 20,
        cursor: str | None = None,
        newest_first: bool = True,
    ) -> PaginatedResult[dict[str, Any]]:
        """List conversations for a user, newest first by default."""
        return self.query(
            user_id,
            index_name="user_conversations-index",
            limit=limit,
            cursor=cursor,
            scan_forward=not newest_first,
        )
