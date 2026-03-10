"""AgentTemplateRepository — DynamoDB access for AgentTemplates table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, GSIConfig, RepositoryConfig
from app.dal.pagination import PaginatedResult


class AgentTemplateRepository(BaseRepository):
    """Repository for the AgentTemplates table.

    Key schema: template_id (HASH)
    GSIs: agent_type-index
    """

    CONFIG = RepositoryConfig(
        table_name="AgentTemplates",
        partition_key="template_id",
        gsi_definitions=[
            GSIConfig(index_name="agent_type-index", partition_key="agent_type"),
        ],
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        """Get a single template by template_id."""
        return self.get_by_id({"template_id": template_id})

    def query_by_agent_type(
        self, agent_type: str, limit: int = 50, cursor: str | None = None
    ) -> PaginatedResult[dict[str, Any]]:
        """List templates by agent type."""
        return self.query(
            agent_type, index_name="agent_type-index", limit=limit, cursor=cursor
        )

    def list_all(self, limit: int = 100) -> PaginatedResult[dict[str, Any]]:
        """Scan all templates (bounded). For admin listing."""
        result = self._table.scan(Limit=limit)
        items = result.get("Items", [])
        return PaginatedResult(items=items, next_cursor=None, count=len(items))
