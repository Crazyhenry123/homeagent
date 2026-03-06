"""Member permission management for agent data access.

Stores and manages permission grants that control what data each agent
can access on behalf of a user. The actual integrations (email, calendar,
HealthKit) are implemented separately — this module only tracks consent
and configuration.
"""

from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key

from app.models.dynamo import get_table

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

    table = get_table("MemberPermissions")
    now = datetime.now(timezone.utc).isoformat()

    item = {
        "user_id": user_id,
        "permission_type": permission_type,
        "config": config,
        "granted_at": now,
        "granted_by": granted_by or user_id,
        "status": "active",
    }
    table.put_item(Item=item)
    return item


def revoke_permission(user_id: str, permission_type: str) -> bool:
    """Revoke a permission by setting status to 'revoked'.

    Returns True if the permission existed, False otherwise.
    """
    if permission_type not in VALID_PERMISSION_TYPES:
        raise ValueError(f"Invalid permission type: {permission_type}")

    table = get_table("MemberPermissions")
    now = datetime.now(timezone.utc).isoformat()

    try:
        table.update_item(
            Key={"user_id": user_id, "permission_type": permission_type},
            UpdateExpression="SET #s = :revoked, revoked_at = :now",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":revoked": "revoked", ":now": now},
            ConditionExpression="attribute_exists(user_id)",
        )
        return True
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return False


def get_permissions(user_id: str) -> list[dict]:
    """Get all permissions for a user (including revoked)."""
    table = get_table("MemberPermissions")
    result = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id),
    )
    return result.get("Items", [])


def get_active_permissions(user_id: str) -> list[dict]:
    """Get only active permissions for a user."""
    all_perms = get_permissions(user_id)
    return [p for p in all_perms if p.get("status") == "active"]


def check_permission(user_id: str, permission_type: str) -> bool:
    """Check if a specific permission is actively granted."""
    if permission_type not in VALID_PERMISSION_TYPES:
        raise ValueError(f"Invalid permission type: {permission_type}")

    table = get_table("MemberPermissions")
    item = table.get_item(
        Key={"user_id": user_id, "permission_type": permission_type}
    ).get("Item")

    return item is not None and item.get("status") == "active"


def delete_all_permissions(user_id: str) -> None:
    """Delete all permissions for a user. Used during member deletion."""
    table = get_table("MemberPermissions")
    last_key = None
    while True:
        kwargs = {
            "KeyConditionExpression": Key("user_id").eq(user_id),
            "ProjectionExpression": "user_id, permission_type",
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        result = table.query(**kwargs)
        with table.batch_writer() as batch:
            for item in result.get("Items", []):
                batch.delete_item(
                    Key={
                        "user_id": item["user_id"],
                        "permission_type": item["permission_type"],
                    }
                )
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
