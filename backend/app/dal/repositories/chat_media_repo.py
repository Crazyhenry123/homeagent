"""ChatMediaRepository — DynamoDB access for ChatMedia table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, RepositoryConfig


class ChatMediaRepository(BaseRepository):
    """Repository for the ChatMedia table.

    Key schema: media_id (HASH)
    TTL: expires_at
    """

    CONFIG = RepositoryConfig(
        table_name="ChatMedia",
        partition_key="media_id",
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def create_with_ttl(self, item: dict[str, Any], expires_at: int) -> dict[str, Any]:
        """Create a media record with a TTL expiration timestamp."""
        item = {**item, "expires_at": expires_at}
        return self.create(item)
