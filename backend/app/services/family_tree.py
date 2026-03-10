from datetime import datetime, timezone

from app.dal import get_dal
from app.services.profile import get_profile

VALID_RELATIONSHIP_TYPES = {"parent_of", "child_of", "spouse_of", "sibling_of"}

INVERSE_MAP = {
    "parent_of": "child_of",
    "child_of": "parent_of",
    "spouse_of": "spouse_of",
    "sibling_of": "sibling_of",
}


def get_relationships(user_id: str) -> list[dict]:
    """Get all relationships for a user."""
    dal = get_dal()
    result = dal.family_relationships.query_by_user(user_id)
    return result.items


def set_relationship(
    user_id: str, related_user_id: str, relationship_type: str
) -> dict:
    """Create a bidirectional relationship between two users.

    Raises ValueError for invalid type or self-relationship.
    """
    if relationship_type not in VALID_RELATIONSHIP_TYPES:
        raise ValueError(
            f"Invalid relationship type: {relationship_type}. "
            f"Must be one of: {', '.join(sorted(VALID_RELATIONSHIP_TYPES))}"
        )
    if user_id == related_user_id:
        raise ValueError("Cannot create a relationship with yourself")

    dal = get_dal()
    now = datetime.now(timezone.utc).isoformat()

    # Forward direction (upsert — put_item without condition)
    forward_item = {
        "user_id": user_id,
        "related_user_id": related_user_id,
        "relationship_type": relationship_type,
        "created_at": now,
    }
    dal.family_relationships._table.put_item(Item=forward_item)

    # Inverse direction
    inverse_type = INVERSE_MAP[relationship_type]
    inverse_item = {
        "user_id": related_user_id,
        "related_user_id": user_id,
        "relationship_type": inverse_type,
        "created_at": now,
    }
    dal.family_relationships._table.put_item(Item=inverse_item)

    return forward_item


def delete_relationship(user_id: str, related_user_id: str) -> None:
    """Delete a relationship in both directions."""
    dal = get_dal()
    dal.family_relationships.delete_relationship(user_id, related_user_id)
    dal.family_relationships.delete_relationship(related_user_id, user_id)


def delete_all_relationships(user_id: str) -> None:
    """Delete all relationships for a user (both directions)."""
    dal = get_dal()

    # Get all relationships where this user is the subject
    result = dal.family_relationships.query_by_user(user_id)
    for item in result.items:
        # Delete the inverse record
        dal.family_relationships.delete_relationship(item["related_user_id"], user_id)
        # Delete the forward record
        dal.family_relationships.delete_relationship(user_id, item["related_user_id"])


def get_family_tree() -> list[dict]:
    """Get all relationships (full scan) for the tree view."""
    dal = get_dal()
    result = dal.family_relationships._table.scan()
    items = result.get("Items", [])

    # Enrich with display names
    user_ids = {item["user_id"] for item in items} | {
        item["related_user_id"] for item in items
    }
    name_map: dict[str, str] = {}
    for uid in user_ids:
        profile = get_profile(uid)
        if profile:
            name_map[uid] = profile.get("display_name", uid)
        else:
            name_map[uid] = uid

    for item in items:
        item["user_name"] = name_map.get(item["user_id"], item["user_id"])
        item["related_user_name"] = name_map.get(
            item["related_user_id"], item["related_user_id"]
        )

    return items


def build_family_context(user_id: str) -> str:
    """Build a natural language description of a user's family relationships.

    Returns an empty string if there are no relationships.
    """
    relationships = get_relationships(user_id)
    if not relationships:
        return ""

    # Group relationships by type
    grouped: dict[str, list[str]] = {}
    for rel in relationships:
        rel_type = rel["relationship_type"]
        related_id = rel["related_user_id"]
        profile = get_profile(related_id)
        name = profile.get("display_name", related_id) if profile else related_id
        grouped.setdefault(rel_type, []).append(name)

    # Build natural language
    parts = []
    label_map = {
        "parent_of": ("Your children are", "Your child is"),
        "child_of": ("Your parents are", "Your parent is"),
        "spouse_of": ("Your spouse/partner is", "Your spouse/partner is"),
        "sibling_of": ("Your siblings are", "Your sibling is"),
    }

    for rel_type, names in grouped.items():
        plural_label, singular_label = label_map.get(
            rel_type, (f"Related ({rel_type}):", f"Related ({rel_type}):")
        )
        if len(names) == 1:
            parts.append(f"{singular_label} {names[0]}.")
        else:
            parts.append(f"{plural_label} {', '.join(names)}.")

    return "Family relationships: " + " ".join(parts)
