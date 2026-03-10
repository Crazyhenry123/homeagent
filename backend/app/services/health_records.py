"""CRUD service for health records.

Supports pluggable storage via optional ``storage`` parameter.
When ``storage`` is None, falls back to DynamoDB (existing behavior).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ulid import ULID

from app.dal import get_dal
from app.services.health_audit import log_audit_event

if TYPE_CHECKING:
    from app.storage.base import StorageProvider

VALID_RECORD_TYPES = {
    "condition",
    "medication",
    "allergy",
    "appointment",
    "vital",
    "immunization",
    "growth",
}

_COLLECTION = "health_records"


def create_health_record(
    user_id: str,
    record_type: str,
    data: dict,
    created_by: str,
    storage: StorageProvider | None = None,
) -> dict:
    """Create a new health record.

    Raises ValueError if record_type is invalid.
    """
    if record_type not in VALID_RECORD_TYPES:
        raise ValueError(
            f"Invalid record_type: {record_type}. "
            f"Must be one of: {', '.join(sorted(VALID_RECORD_TYPES))}"
        )

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

    if storage is not None:
        storage.put_record(_COLLECTION, item)
    else:
        dal = get_dal()
        dal.health_records.create(item)

    # Audit log always goes to local DynamoDB
    log_audit_event(
        record_id=record_id,
        user_id=user_id,
        actor_id=created_by,
        action="create",
        record_snapshot=item,
    )

    return item


def get_health_record(
    user_id: str,
    record_id: str,
    storage: StorageProvider | None = None,
) -> dict | None:
    """Get a single health record by user_id and record_id."""
    if storage is not None:
        return storage.get_record(
            _COLLECTION, {"user_id": user_id, "record_id": record_id}
        )

    dal = get_dal()
    return dal.health_records.get_by_id({"user_id": user_id, "record_id": record_id})


def list_health_records(
    user_id: str,
    record_type: str | None = None,
    storage: StorageProvider | None = None,
) -> list[dict]:
    """List health records for a user, optionally filtered by record_type."""
    if storage is not None:
        key_condition: dict = {"user_id": user_id}
        if record_type:
            key_condition["record_type"] = record_type
            return storage.query_records(
                _COLLECTION,
                key_condition,
                index_name="record_type-index",
            )
        return storage.query_records(_COLLECTION, key_condition)

    dal = get_dal()

    if record_type:
        result = dal.health_records.query_by_record_type(user_id, record_type)
    else:
        result = dal.health_records.query_by_user(user_id)

    return result.items


def update_health_record(
    user_id: str,
    record_id: str,
    updates: dict,
    actor_id: str | None = None,
    storage: StorageProvider | None = None,
) -> dict | None:
    """Update a health record's data and/or record_type.

    Allowed fields: data, record_type.
    Returns updated item or None if not found.
    """
    allowed_fields = {"data", "record_type"}
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}
    if not filtered:
        return get_health_record(user_id, record_id, storage=storage)

    if "record_type" in filtered and filtered["record_type"] not in VALID_RECORD_TYPES:
        raise ValueError(f"Invalid record_type: {filtered['record_type']}")

    # Capture before-state for audit
    before = get_health_record(user_id, record_id, storage=storage)

    if storage is not None:
        if before is None:
            return None
        merged = {**before, **filtered}
        merged["updated_at"] = datetime.now(timezone.utc).isoformat()
        storage.put_record(_COLLECTION, merged)

        if actor_id:
            log_audit_event(
                record_id=record_id,
                user_id=user_id,
                actor_id=actor_id,
                action="update",
                changes={"before": before, "after": merged},
            )
        return merged

    dal = get_dal()
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
        result = dal.health_records._table.update_item(
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
    except (
        dal.health_records._table.meta.client.exceptions.ConditionalCheckFailedException
    ):
        return None


def delete_health_record(
    user_id: str,
    record_id: str,
    actor_id: str | None = None,
    storage: StorageProvider | None = None,
) -> bool:
    """Delete a single health record. Returns True if it existed."""
    snapshot = (
        get_health_record(user_id, record_id, storage=storage) if actor_id else None
    )

    if storage is not None:
        deleted = storage.delete_record(
            _COLLECTION, {"user_id": user_id, "record_id": record_id}
        )
        if actor_id and snapshot:
            log_audit_event(
                record_id=record_id,
                user_id=user_id,
                actor_id=actor_id,
                action="delete",
                record_snapshot=snapshot,
            )
        return deleted

    dal = get_dal()
    try:
        dal.health_records._table.delete_item(
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
    except (
        dal.health_records._table.meta.client.exceptions.ConditionalCheckFailedException
    ):
        return False


def delete_all_health_records(
    user_id: str,
    storage: StorageProvider | None = None,
) -> None:
    """Delete all health records for a user (cascade delete)."""
    if storage is not None:
        storage.delete_all_records(_COLLECTION, {"user_id": user_id})
        return

    dal = get_dal()
    result = dal.health_records.query_by_user(user_id)
    if result.items:
        dal.health_records.batch_delete(
            [
                {"user_id": item["user_id"], "record_id": item["record_id"]}
                for item in result.items
            ]
        )


def get_health_summary(
    user_id: str,
    storage: StorageProvider | None = None,
) -> dict:
    """Build a structured health summary grouped by record type."""
    records = list_health_records(user_id, storage=storage)
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
