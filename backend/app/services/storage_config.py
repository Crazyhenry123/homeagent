"""Service for user storage provider configuration — stub for migration branch."""

from datetime import datetime, timezone

from app.dal import get_dal

VALID_PROVIDERS = {"local", "google_drive", "onedrive", "dropbox", "box"}


def get_storage_config(user_id: str) -> dict | None:
    """Get user's storage provider configuration."""
    try:
        dal = get_dal()
        return dal.storage_config.get_config(user_id)
    except Exception:
        return None


def set_storage_config(
    user_id: str, provider: str, provider_config: dict | None = None
) -> dict:
    """Set or update user's storage provider."""
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Invalid provider: {provider}")

    dal = get_dal()
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "user_id": user_id,
        "provider": provider,
        "provider_config": provider_config or {},
        "status": "active",
        "connected_at": now,
        "updated_at": now,
    }
    dal.storage_config.upsert(item)
    return item


def update_storage_status(user_id: str, status: str) -> dict | None:
    """Update the status field."""
    dal = get_dal()
    now = datetime.now(timezone.utc).isoformat()
    try:
        result = dal.storage_config._table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET #s = :s, updated_at = :u",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": status, ":u": now},
            ConditionExpression="attribute_exists(user_id)",
            ReturnValues="ALL_NEW",
        )
        return result.get("Attributes")
    except Exception:
        return None


def clear_storage_config(user_id: str) -> None:
    """Remove storage config (reverts to local)."""
    dal = get_dal()
    dal.storage_config.delete({"user_id": user_id})
