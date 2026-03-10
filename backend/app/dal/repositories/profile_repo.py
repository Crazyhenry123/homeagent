"""ProfileRepository — DynamoDB access for MemberProfiles table."""

from __future__ import annotations

from typing import Any

from app.dal.base import BaseRepository, RepositoryConfig


class ProfileRepository(BaseRepository):
    """Repository for the MemberProfiles table.

    Key schema: user_id (HASH)
    """

    CONFIG = RepositoryConfig(
        table_name="MemberProfiles",
        partition_key="user_id",
    )

    def __init__(self, dynamodb_resource: Any, table_prefix: str = "") -> None:
        super().__init__(self.CONFIG, dynamodb_resource, table_prefix)

    def get_profile(self, user_id: str) -> dict[str, Any] | None:
        """Get a user's profile by user_id."""
        return self.get_by_id({"user_id": user_id})

    def batch_get_by_user_ids(self, user_ids: list[str]) -> list[dict[str, Any]]:
        """Batch fetch profiles for multiple users."""
        keys = [{"user_id": uid} for uid in user_ids]
        return self.batch_get(keys)
