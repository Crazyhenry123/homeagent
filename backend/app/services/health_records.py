"""CRUD service for the HealthRecords DynamoDB table."""

from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key
from ulid import ULID

from app.models.dynamo import get_table
from app.services.health_audit import log_audit_event

VALID_RECORD_TYPES = {
    "condition",
    "medication",
    "allergy",
    "appointment",
    "vital",
    "immunization",
    "growth",
}


def create_health_record(
    user_id: str,
    record_type: str,
    data: dict,
    created_by: str,
) -> dict:
    """Create a new health record.

    Raises ValueError if record_type is invalid.
    """
    if record_type not in VALID_RECORD_TYPES:
        raise ValueError(
            f"Invalid record_type: {record_type}. "
            f"Must be one of: {', '.join(sorted(VALID_RECORD_TYPES))}"
        )

    table = get_table("HealthRecords")
    now = datetime.now(timezone.utc).isoformat()
    record_id = str(ULID())

    item = {
        "user_id": user_id,
        "record_id": record_id,
        "record_type": record_type,
        "data": data,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
    table.put_item(Item=item)

    log_audit_event(
        record_id=record_id,
        user_id=user_id,
        actor_id=created_by,
        action="create",
        record_snapshot=item,
    )

    return item


def get_health_record(user_id: str, record_id: str) -> dict | None:
    """Get a single health record by user_id and record_id."""
    table = get_table("HealthRecords")
    result = table.get_item(Key={"user_id": user_id, "record_id": record_id})
    return result.get("Item")


def list_health_records(
    user_id: str,
    record_type: str | None = None,
) -> list[dict]:
    """List health records for a user, optionally filtered by record_type."""
    table = get_table("HealthRecords")

    if record_type:
        result = table.query(
            IndexName="record_type-index",
            KeyConditionExpression=(
                Key("user_id").eq(user_id) & Key("record_type").eq(record_type)
            ),
        )
    else:
        result = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id),
        )

    return result.get("Items", [])


def update_health_record(
    user_id: str,
    record_id: str,
    updates: dict,
    actor_id: str | None = None,
) -> dict | None:
    """Update a health record's data and/or record_type.

    Allowed fields: data, record_type.
    Returns updated item or None if not found.
    """
    allowed_fields = {"data", "record_type"}
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}
    if not filtered:
        return get_health_record(user_id, record_id)

    if "record_type" in filtered and filtered["record_type"] not in VALID_RECORD_TYPES:
        raise ValueError(f"Invalid record_type: {filtered['record_type']}")

    # Capture before-state for audit
    before = get_health_record(user_id, record_id)

    table = get_table("HealthRecords")
    now = datetime.now(timezone.utc).isoformat()
    filtered["updated_at"] = now

    expr_parts = []
    expr_names = {}
    expr_values = {}
    for i, (key, value) in enumerate(filtered.items()):
        attr_name = f"#k{i}"
        attr_value = f":v{i}"
        expr_parts.append(f"{attr_name} = {attr_value}")
        expr_names[attr_name] = key
        expr_values[attr_value] = value

    try:
        result = table.update_item(
            Key={"user_id": user_id, "record_id": record_id},
            UpdateExpression="SET " + ", ".join(expr_parts),
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
            ConditionExpression="attribute_exists(user_id)",
            ReturnValues="ALL_NEW",
        )
        updated = result["Attributes"]

        if actor_id and before:
            log_audit_event(
                record_id=record_id,
                user_id=user_id,
                actor_id=actor_id,
                action="update",
                changes={"before": before, "after": updated},
            )

        return updated
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return None


def delete_health_record(
    user_id: str, record_id: str, actor_id: str | None = None
) -> bool:
    """Delete a single health record. Returns True if it existed."""
    # Capture snapshot for audit before deleting
    snapshot = get_health_record(user_id, record_id) if actor_id else None

    table = get_table("HealthRecords")
    try:
        table.delete_item(
            Key={"user_id": user_id, "record_id": record_id},
            ConditionExpression="attribute_exists(user_id)",
        )
        if actor_id and snapshot:
            log_audit_event(
                record_id=record_id,
                user_id=user_id,
                actor_id=actor_id,
                action="delete",
                record_snapshot=snapshot,
            )
        return True
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return False


def delete_all_health_records(user_id: str) -> None:
    """Delete all health records for a user (cascade delete)."""
    table = get_table("HealthRecords")
    result = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        ProjectionExpression="user_id, record_id",
    )
    with table.batch_writer() as batch:
        for item in result.get("Items", []):
            batch.delete_item(
                Key={"user_id": item["user_id"], "record_id": item["record_id"]}
            )


def get_health_summary(user_id: str) -> dict:
    """Build a structured health summary grouped by record type."""
    records = list_health_records(user_id)
    summary: dict[str, list[dict]] = {}
    for record in records:
        rt = record["record_type"]
        summary.setdefault(rt, []).append(
            {
                "record_id": record["record_id"],
                "data": record["data"],
                "created_at": record["created_at"],
                "updated_at": record["updated_at"],
            }
        )
    return {"user_id": user_id, "record_count": len(records), "by_type": summary}
