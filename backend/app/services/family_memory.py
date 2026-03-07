"""Family shared memory service — manages memory sharing between family members.

Each member configures what parts of their profile and conversation insights
they share with the family. The aggregated shared context is injected into
each member's agent system prompt so the agent has family awareness.
"""

import logging
from datetime import datetime, timezone

from app.models.dynamo import get_table
from app.services.profile import get_profile

logger = logging.getLogger(__name__)

DEFAULT_SHARING_CONFIG = {
    "share_profile": True,
    "share_interests": True,
    "share_health_notes": False,
    "share_conversation_insights": False,
    "sharing_level": "basic",  # "none", "basic", "full"
    "custom_shared_info": "",
}


def get_sharing_config(user_id: str) -> dict:
    """Get a member's memory sharing configuration.

    Returns the stored config or defaults if none exists.
    """
    table = get_table("MemorySharingConfig")
    result = table.get_item(Key={"user_id": user_id})
    item = result.get("Item")
    if not item:
        return {"user_id": user_id, **DEFAULT_SHARING_CONFIG}
    return item


def update_sharing_config(user_id: str, updates: dict) -> dict:
    """Update a member's memory sharing configuration.

    Only allowed fields are updated. Returns the full updated config.
    """
    allowed_fields = {
        "share_profile",
        "share_interests",
        "share_health_notes",
        "share_conversation_insights",
        "sharing_level",
        "custom_shared_info",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}
    if not filtered:
        return get_sharing_config(user_id)

    # Validate sharing_level
    if "sharing_level" in filtered:
        if filtered["sharing_level"] not in ("none", "basic", "full"):
            raise ValueError("sharing_level must be 'none', 'basic', or 'full'")

    table = get_table("MemorySharingConfig")
    now = datetime.now(timezone.utc).isoformat()
    filtered["updated_at"] = now

    # Upsert: get existing or create with defaults
    existing = get_sharing_config(user_id)
    existing.update(filtered)
    existing["user_id"] = user_id
    table.put_item(Item=existing)
    return existing


def _get_family_member_ids(user_id: str) -> list[str]:
    """Get all family member user_ids for the same family as user_id."""
    table = get_table("FamilyMembers")

    # Scan FamilyMembers to find this user's family_id
    # (FamilyMembers has composite key: family_id HASH, user_id RANGE)
    from boto3.dynamodb.conditions import Attr

    result = table.scan(FilterExpression=Attr("user_id").eq(user_id))
    items = result.get("Items", [])
    if not items:
        return []

    family_id = items[0]["family_id"]

    # Get all members of this family
    from boto3.dynamodb.conditions import Key

    members_result = table.query(
        KeyConditionExpression=Key("family_id").eq(family_id)
    )
    member_ids = [
        m["user_id"]
        for m in members_result.get("Items", [])
        if m["user_id"] != user_id
    ]
    return member_ids


def get_family_shared_context(user_id: str) -> str:
    """Build a shared family context string for system prompt injection.

    Aggregates shared information from all family members based on their
    individual sharing configurations.
    """
    member_ids = _get_family_member_ids(user_id)
    if not member_ids:
        return ""

    context_parts = []

    for mid in member_ids:
        sharing = get_sharing_config(mid)

        # Skip if sharing is disabled
        if sharing.get("sharing_level") == "none":
            continue

        profile = get_profile(mid)
        if not profile:
            continue

        member_info = []
        display_name = profile.get("display_name", "A family member")

        if sharing.get("share_profile"):
            family_role = profile.get("family_role", "")
            if family_role:
                member_info.append(f"role: {family_role}")

        if sharing.get("share_interests"):
            interests = profile.get("interests", [])
            if interests:
                member_info.append(f"interests: {', '.join(interests)}")

        if sharing.get("share_health_notes") and sharing.get("sharing_level") == "full":
            health_notes = profile.get("health_notes", "")
            if health_notes:
                member_info.append(f"health notes: {health_notes}")

        custom = sharing.get("custom_shared_info", "")
        if custom:
            member_info.append(f"shared info: {custom}")

        if member_info:
            info_str = "; ".join(member_info)
            context_parts.append(f"[{display_name}] {info_str}")

    if not context_parts:
        return ""

    header = "\nFamily context (shared by family members):"
    return header + "\n" + "\n".join(f"- {p}" for p in context_parts)
