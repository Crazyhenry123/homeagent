from datetime import datetime, timezone

from app.models.dynamo import get_table


def get_profile(user_id: str) -> dict | None:
    """Get a member profile by user_id."""
    table = get_table("MemberProfiles")
    item = table.get_item(Key={"user_id": user_id}).get("Item")
    return item


def create_profile(
    user_id: str,
    display_name: str,
    role: str = "member",
) -> dict:
    """Create a default member profile."""
    table = get_table("MemberProfiles")
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "user_id": user_id,
        "display_name": display_name,
        "family_role": "",
        "preferences": {},
        "health_notes": "",
        "interests": [],
        "role": role,
        "created_at": now,
        "updated_at": now,
    }
    table.put_item(Item=item)
    return item


def update_profile(user_id: str, updates: dict) -> dict | None:
    """Update a member profile with the given fields.

    Allowed fields: display_name, family_role, preferences, health_notes, interests.
    Returns the updated profile or None if not found.
    """
    allowed_fields = {
        "display_name",
        "family_role",
        "preferences",
        "health_notes",
        "interests",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}
    if not filtered:
        return get_profile(user_id)

    table = get_table("MemberProfiles")
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
            Key={"user_id": user_id},
            UpdateExpression="SET " + ", ".join(expr_parts),
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
            ConditionExpression="attribute_exists(user_id)",
            ReturnValues="ALL_NEW",
        )
        return result["Attributes"]
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return None


def list_profiles() -> list[dict]:
    """List all member profiles (admin use)."""
    table = get_table("MemberProfiles")
    result = table.scan()
    return result.get("Items", [])
