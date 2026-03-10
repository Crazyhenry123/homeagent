from datetime import datetime, timezone

from app.dal import get_dal
from app.dal.exceptions import EntityNotFoundError


def get_profile(user_id: str) -> dict | None:
    """Get a member profile by user_id."""
    dal = get_dal()
    return dal.profiles.get_profile(user_id)


def create_profile(
    user_id: str,
    display_name: str,
    role: str = "member",
) -> dict:
    """Create a default member profile."""
    dal = get_dal()
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
    dal.profiles.create(item)
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

    dal = get_dal()
    try:
        return dal.profiles.update({"user_id": user_id}, filtered)
    except EntityNotFoundError:
        return None


def list_profiles() -> list[dict]:
    """List all member profiles (admin use)."""
    dal = get_dal()
    result = dal.profiles._table.scan()
    return result.get("Items", [])
