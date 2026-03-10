import logging
from datetime import datetime, timezone

from ulid import ULID

from app.dal import get_dal
from app.dal.exceptions import DuplicateEntityError

logger = logging.getLogger(__name__)


def create_family(owner_user_id: str, family_name: str) -> dict:
    """Create a new family record and add the owner as the first member.

    Returns the created family dict.
    """
    dal = get_dal()
    family_id = str(ULID())
    now = datetime.now(timezone.utc).isoformat()

    try:
        dal.families.create(
            {
                "family_id": family_id,
                "name": family_name,
                "owner_user_id": owner_user_id,
                "created_at": now,
            }
        )
    except DuplicateEntityError:
        raise ValueError("Family already exists (duplicate creation detected)")

    # Add owner as first member
    add_member_to_family(family_id, owner_user_id, role="owner")

    # Update user record with family_id
    dal.users.update({"user_id": owner_user_id}, {"family_id": family_id})

    return {
        "family_id": family_id,
        "name": family_name,
        "owner_user_id": owner_user_id,
        "created_at": now,
    }


def get_family(family_id: str) -> dict | None:
    """Get family details by family_id."""
    dal = get_dal()
    return dal.families.get_family(family_id)


def get_family_by_owner(owner_user_id: str) -> dict | None:
    """Get a family by owner user ID."""
    dal = get_dal()
    return dal.families.get_by_owner(owner_user_id)


def get_user_family_id(user_id: str) -> str | None:
    """Get the family_id for a user from the Users table."""
    dal = get_dal()
    user = dal.users.get_user(user_id)
    if not user:
        return None
    return user.get("family_id")


def get_family_members(family_id: str) -> list[dict]:
    """List all members of a family."""
    dal = get_dal()
    result = dal.memberships.query_by_family(family_id)
    members = result.items

    # Enrich with user info (batch get for efficiency)
    user_ids = [m["user_id"] for m in members]
    if user_ids:
        users = dal.users.batch_get([{"user_id": uid} for uid in user_ids])
        user_map = {u["user_id"]: u for u in users}
    else:
        user_map = {}

    enriched = []
    for member in members:
        user = user_map.get(member["user_id"])
        enriched.append(
            {
                **member,
                "name": user.get("name", "Unknown") if user else "Unknown",
            }
        )

    return enriched


def add_member_to_family(family_id: str, user_id: str, role: str = "member") -> dict:
    """Add a user to a family. Returns the membership record."""
    dal = get_dal()
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "family_id": family_id,
        "user_id": user_id,
        "role": role,
        "joined_at": now,
    }
    dal.memberships.create(item)

    # Update user record with family_id
    dal.users.update({"user_id": user_id}, {"family_id": family_id})

    return item


def get_family_settings(family_id: str) -> dict:
    """Get the settings map for a family. Returns defaults if not set."""
    family = get_family(family_id)
    if not family:
        return {"web_search_enabled": True}
    return family.get("settings", {"web_search_enabled": True})


def update_family_settings(family_id: str, settings: dict) -> dict:
    """Update family settings. Merges with existing settings."""
    dal = get_dal()
    allowed_keys = {"web_search_enabled"}
    filtered = {k: v for k, v in settings.items() if k in allowed_keys}
    if not filtered:
        raise ValueError(f"No valid settings provided. Allowed: {allowed_keys}")

    # Merge with existing
    current = get_family_settings(family_id)
    current.update(filtered)

    dal.families.update({"family_id": family_id}, {"settings": current})
    return current


def remove_member_from_family(family_id: str, user_id: str) -> None:
    """Remove a member from a family."""
    dal = get_dal()
    dal.memberships.delete_membership(family_id, user_id)

    # Remove family_id from user record
    dal.users._table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="REMOVE family_id",
    )
