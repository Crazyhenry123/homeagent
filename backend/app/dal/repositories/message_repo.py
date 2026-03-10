"""MessageRepository — DynamoDB access for Messages table."""

from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key

from app.dal.base import BaseRepository, RepositoryConfig
from app.dal.pagination import PaginatedResult


class MessageRepository(BaseRepository):
    """Repository for the Messages table.

    Key schema: conversation_id (HASH), sort_key (RANGE)
    """

    CONFIG = RepositoryConfig(
        table_name="Messages",
        partition_key="conversation_id",
        sort_key="sort_key",
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def query_by_conversation(
        self,
        conversation_id: str,
        limit: int = 50,
        cursor: str | None = None,
        newest_first: bool = False,
    ) -> PaginatedResult[dict[str, Any]]:
        """List messages in a conversation, oldest first by default."""
        return self.query(
            conversation_id,
            limit=limit,
            cursor=cursor,
            scan_forward=not newest_first,
        )

    def query_by_conversation_after(
        self,
        conversation_id: str,
        after_sort_key: str,
        limit: int = 50,
    ) -> PaginatedResult[dict[str, Any]]:
        """Get messages after a given sort_key (for incremental fetches)."""
        return self.query(
            conversation_id,
            sort_condition=Key("sort_key").gt(after_sort_key),
            limit=limit,
        )

    def delete_by_conversation(self, conversation_id: str) -> None:
        """Delete all messages in a conversation (batch)."""
        all_keys: list[dict[str, Any]] = []
        cursor = None
        while True:
            page = self.query(conversation_id, limit=100, cursor=cursor)
            all_keys.extend(
                {"conversation_id": m["conversation_id"], "sort_key": m["sort_key"]}
                for m in page.items
            )
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        if all_keys:
            self.batch_delete(all_keys)
