"""CRUD service for health observations.

Supports pluggable storage via optional ``storage`` parameter.
When ``storage`` is None, falls back to DynamoDB (existing behavior).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from boto3.dynamodb.conditions import Key
from ulid import ULID

from app.models.dynamo import get_table

if TYPE_CHECKING:
    from app.storage.base import StorageProvider

VALID_CATEGORIES = {"diet", "exercise", "sleep", "symptom", "mood", "general"}

_COLLECTION = "health_observations"


def create_observation(
    user_id: str,
    category: str,
    summary: str,
    detail: str = "",
    source_conversation_id: str | None = None,
    confidence: str = "medium",
    observed_at: str | None = None,
    storage: StorageProvider | None = None,
) -> dict:
    """Create a new health observation.

    Raises ValueError if category is invalid.
    """
    if category not in VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category: {category}. "
            f"Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"
        )

    now = datetime.now(timezone.utc).isoformat()
    observation_id = str(ULID())

    item = {
        "user_id": user_id,
        "observation_id": observation_id,
        "category": category,
        "summary": summary,
        "detail": detail,
        "confidence": confidence,
        "observed_at": observed_at or now,
        "created_at": now,
    }
    if source_conversation_id:
        item["source_conversation_id"] = source_conversation_id

    if storage is not None:
        storage.put_record(_COLLECTION, item)
    else:
        table = get_table("HealthObservations")
        table.put_item(Item=item)

    return item


def list_observations(
    user_id: str,
    category: str | None = None,
    storage: StorageProvider | None = None,
) -> list[dict]:
    """List health observations for a user, optionally filtered by category."""
    if storage is not None:
        key_condition: dict = {"user_id": user_id}
        if category:
            key_condition["category"] = category
            return storage.query_records(
                _COLLECTION,
                key_condition,
                index_name="category-index",
            )
        return storage.query_records(_COLLECTION, key_condition)

    table = get_table("HealthObservations")

    if category:
        result = table.query(
            IndexName="category-index",
            KeyConditionExpression=(
                Key("user_id").eq(user_id) & Key("category").eq(category)
            ),
        )
    else:
        result = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id),
        )

    return result.get("Items", [])


def delete_all_observations(
    user_id: str,
    storage: StorageProvider | None = None,
) -> None:
    """Delete all health observations for a user (cascade delete)."""
    if storage is not None:
        storage.delete_all_records(_COLLECTION, {"user_id": user_id})
        return

    table = get_table("HealthObservations")
    result = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        ProjectionExpression="user_id, observation_id",
    )
    with table.batch_writer() as batch:
        for item in result.get("Items", []):
            batch.delete_item(
                Key={
                    "user_id": item["user_id"],
                    "observation_id": item["observation_id"],
                }
            )
