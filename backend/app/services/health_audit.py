"""Audit trail service for health record changes."""

from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key
from ulid import ULID

from app.models.dynamo import get_table


def log_audit_event(
    record_id: str,
    user_id: str,
    actor_id: str,
    action: str,
    changes: dict | None = None,
    record_snapshot: dict | None = None,
) -> dict:
    """Write an audit log entry for a health record change.

    Args:
        record_id: The health record that was changed.
        user_id: The user who owns the health record.
        actor_id: The user who performed the action.
        action: One of 'create', 'update', 'delete'.
        changes: Before/after dict for updates.
        record_snapshot: Full record for create/delete actions.
    """
    table = get_table("HealthAuditLog")
    now = datetime.now(timezone.utc).isoformat()
    audit_id = str(ULID())
    audit_sk = f"{now}#{audit_id}"

    item = {
        "record_id": record_id,
        "audit_sk": audit_sk,
        "audit_id": audit_id,
        "user_id": user_id,
        "actor_id": actor_id,
        "action": action,
        "created_at": now,
    }
    if changes is not None:
        item["changes"] = changes
    if record_snapshot is not None:
        item["record_snapshot"] = record_snapshot

    table.put_item(Item=item)
    return item


def list_audit_log(record_id: str) -> list[dict]:
    """List audit entries for a specific health record, newest first."""
    table = get_table("HealthAuditLog")
    result = table.query(
        KeyConditionExpression=Key("record_id").eq(record_id),
        ScanIndexForward=False,
    )
    return result.get("Items", [])


def list_user_audit_log(user_id: str) -> list[dict]:
    """List all audit entries for a user, newest first."""
    table = get_table("HealthAuditLog")
    result = table.query(
        IndexName="user-audit-index",
        KeyConditionExpression=Key("user_id").eq(user_id),
        ScanIndexForward=False,
    )
    return result.get("Items", [])
