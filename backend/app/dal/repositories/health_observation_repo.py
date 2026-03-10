"""HealthObservationRepository — DynamoDB access for HealthObservations table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, GSIConfig, RepositoryConfig
from app.dal.pagination import PaginatedResult


class HealthObservationRepository(BaseRepository):
    """Repository for the HealthObservations table.

    Key schema: user_id (HASH), observation_id (RANGE)
    GSIs: category-index (PK: user_id, SK: category)
    """

    CONFIG = RepositoryConfig(
        table_name="HealthObservations",
        partition_key="user_id",
        sort_key="observation_id",
        gsi_definitions=[
            GSIConfig(
                index_name="category-index",
                partition_key="user_id",
                sort_key="category",
            ),
        ],
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def query_by_user(
        self, user_id: str, limit: int = 50, cursor: str | None = None
    ) -> PaginatedResult[dict[str, Any]]:
        """List all observations for a user."""
        return self.query(user_id, limit=limit, cursor=cursor)

    def query_by_category(
        self,
        user_id: str,
        category: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> PaginatedResult[dict[str, Any]]:
        """List observations filtered by category via category-index."""
        from boto3.dynamodb.conditions import Key

        return self.query(
            user_id,
            sort_condition=Key("category").eq(category),
            index_name="category-index",
            limit=limit,
            cursor=cursor,
        )

    def get_observation(
        self, user_id: str, observation_id: str
    ) -> dict[str, Any] | None:
        """Get a specific observation."""
        return self.get_by_id({"user_id": user_id, "observation_id": observation_id})
