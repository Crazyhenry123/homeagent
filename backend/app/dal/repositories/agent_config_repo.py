"""AgentConfigRepository — DynamoDB access for AgentConfigs table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, RepositoryConfig
from app.dal.pagination import PaginatedResult


class AgentConfigRepository(BaseRepository):
    """Repository for the AgentConfigs table.

    Key schema: user_id (HASH), agent_type (RANGE)
    """

    CONFIG = RepositoryConfig(
        table_name="AgentConfigs",
        partition_key="user_id",
        sort_key="agent_type",
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def query_by_user(
        self, user_id: str, limit: int = 50, cursor: str | None = None
    ) -> PaginatedResult[dict[str, Any]]:
        """List all agent configs for a user."""
        return self.query(user_id, limit=limit, cursor=cursor)

    def get_config(self, user_id: str, agent_type: str) -> dict[str, Any] | None:
        """Get a specific agent config by user and agent type."""
        return self.get_by_id({"user_id": user_id, "agent_type": agent_type})

    def delete_config(self, user_id: str, agent_type: str) -> None:
        """Delete a specific agent config."""
        self.delete({"user_id": user_id, "agent_type": agent_type})
