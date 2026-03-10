"""Member permission management for agent data access.

Stores and manages permission grants that control what data each agent
can access on behalf of a user. The actual integrations (email, calendar,
HealthKit) are implemented separately — this module only tracks consent
and configuration.
"""

from datetime import datetime, timezone

from app.dal import get_dal

VALID_PERMISSION_TYPES = {
    "email_access",
    "calendar_access",
    "health_data",
    "medical_records",
}


def grant_permission(
    user_id: str,
    permission_type: str,
    config: dict,
    granted_by: str | None = None,
) -> dict:
    """Store a permission grant with configuration.

    Config schemas per permission_type:
      - email_access: {email_address: str, provider: str}
      - calendar_access: {calendar_id: str, provider: str}
      - health_data: {consent_given: bool, data_sources: list[str]}
      - medical_records: {folder_path: str, s3_prefix: str}

    Raises ValueError if permission_type is not recognized.
    """
    if permission_type not in VALID_PERMISSION_TYPES:
        raise ValueError(f"Invalid permission type: {permission_type}")

    dal = get_dal()
    now = datetime.now(timezone.utc).isoformat()

    item = {
        "user_id": user_id,
        "permission_type": permission_type,
        "config": config,
        "granted_at": now,
        "granted_by": granted_by or user_id,
        "status": "active",
    }
    dal.member_permissions._table.put_item(Item=item)
    return item


def revoke_permission(user_id: str, permission_type: str) -> bool:
    """Revoke a permission by setting status to 'revoked'.

    Returns True if the permission existed, False otherwise.
    """
    if permission_type not in VALID_PERMISSION_TYPES:
        raise ValueError(f"Invalid permission type: {permission_type}")

    dal = get_dal()
    now = datetime.now(timezone.utc).isoformat()

    try:
        dal.member_permissions._table.update_item(
            Key={"user_id": user_id, "permission_type": permission_type},
            UpdateExpression="SET #s = :revoked, revoked_at = :now",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":revoked": "revoked", ":now": now},
            ConditionExpression="attribute_exists(user_id)",
        )
        return True
    except dal.member_permissions._table.meta.client.exceptions.ConditionalCheckFailedException:
        return False


def get_permissions(user_id: str) -> list[dict]:
    """Get all permissions for a user (including revoked)."""
    dal = get_dal()
    result = dal.member_permissions.query_by_user(user_id)
    return result.items


def get_active_permissions(user_id: str) -> list[dict]:
    """Get only active permissions for a user."""
    all_perms = get_permissions(user_id)
    return [p for p in all_perms if p.get("status") == "active"]


def check_permission(user_id: str, permission_type: str) -> bool:
    """Check if a specific permission is actively granted."""
    if permission_type not in VALID_PERMISSION_TYPES:
        raise ValueError(f"Invalid permission type: {permission_type}")

    dal = get_dal()
    item = dal.member_permissions.get_permission(user_id, permission_type)
    return item is not None and item.get("status") == "active"


def delete_all_permissions(user_id: str) -> None:
    """Delete all permissions for a user. Used during member deletion."""
    dal = get_dal()
    result = dal.member_permissions.query_by_user(user_id)
    if result.items:
        dal.member_permissions.batch_delete(
            [
                {"user_id": item["user_id"], "permission_type": item["permission_type"]}
                for item in result.items
            ]
        )
