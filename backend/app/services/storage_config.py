"""CRUD operations for the StorageConfig DynamoDB table."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.dynamo import get_table


def get_storage_config(user_id: str) -> dict[str, Any] | None:
    """Return the storage configuration for a user, or None."""
    table = get_table("StorageConfig")
    result = table.get_item(Key={"user_id": user_id})
    return result.get("Item")


def set_storage_config(
    user_id: str,
    provider: str,
    *,
    status: str = "active",
) -> dict[str, Any]:
    """Create or replace a user's storage configuration."""
    table = get_table("StorageConfig")
    now = datetime.now(timezone.utc).isoformat()
    item: dict[str, Any] = {
        "user_id": user_id,
        "provider": provider,
        "status": status,
        "updated_at": now,
    }
    table.put_item(Item=item)
    return item


def update_storage_status(user_id: str, status: str) -> dict[str, Any] | None:
    """Update the status field of an existing storage configuration."""
    table = get_table("StorageConfig")
    try:
        response = table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET #s = :s, updated_at = :u",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": status,
                ":u": datetime.now(timezone.utc).isoformat(),
            },
            ReturnValues="ALL_NEW",
            ConditionExpression="attribute_exists(user_id)",
        )
        return response.get("Attributes")
    except Exception:
        return None


def clear_storage_config(user_id: str) -> bool:
    """Delete a user's storage configuration (reverts to local)."""
    table = get_table("StorageConfig")
    table.delete_item(Key={"user_id": user_id})
    return True
