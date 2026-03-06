import logging
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from ulid import ULID

from app.models.dynamo import get_table

logger = logging.getLogger(__name__)


def create_family(owner_user_id: str, family_name: str) -> dict:
    """Create a new family record and add the owner as the first member.

    Returns the created family dict.
    """
    family_id = str(ULID())
    now = datetime.now(timezone.utc).isoformat()

    families_table = get_table("Families")
    try:
        families_table.put_item(
            Item={
                "family_id": family_id,
                "name": family_name,
                "owner_user_id": owner_user_id,
                "created_at": now,
            },
            ConditionExpression="attribute_not_exists(family_id)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ValueError("Family already exists (duplicate creation detected)")
        raise

    # Add owner as first member
    add_member_to_family(family_id, owner_user_id, role="owner")

    # Update user record with family_id
    users_table = get_table("Users")
    users_table.update_item(
        Key={"user_id": owner_user_id},
        UpdateExpression="SET family_id = :fid",
        ExpressionAttributeValues={":fid": family_id},
    )

    return {
        "family_id": family_id,
        "name": family_name,
        "owner_user_id": owner_user_id,
        "created_at": now,
    }


def get_family(family_id: str) -> dict | None:
    """Get family details by family_id."""
    families_table = get_table("Families")
    item = families_table.get_item(Key={"family_id": family_id}).get("Item")
    return item


def get_family_by_owner(owner_user_id: str) -> dict | None:
    """Get a family by owner user ID."""
    families_table = get_table("Families")
    result = families_table.query(
        IndexName="owner-index",
        KeyConditionExpression=Key("owner_user_id").eq(owner_user_id),
        Limit=1,
    )
    items = result.get("Items", [])
    return items[0] if items else None


def get_user_family_id(user_id: str) -> str | None:
    """Get the family_id for a user from the Users table."""
    users_table = get_table("Users")
    user = users_table.get_item(Key={"user_id": user_id}).get("Item")
    if not user:
        return None
    return user.get("family_id")


def get_family_members(family_id: str) -> list[dict]:
    """List all members of a family."""
    members_table = get_table("FamilyMembers")
    result = members_table.query(
        KeyConditionExpression=Key("family_id").eq(family_id),
    )
    members = result.get("Items", [])

    # Enrich with user info
    users_table = get_table("Users")
    enriched = []
    for member in members:
        user = users_table.get_item(Key={"user_id": member["user_id"]}).get("Item")
        enriched.append(
            {
                **member,
                "name": user.get("name", "Unknown") if user else "Unknown",
            }
        )

    return enriched


def add_member_to_family(family_id: str, user_id: str, role: str = "member") -> dict:
    """Add a user to a family. Returns the membership record."""
    now = datetime.now(timezone.utc).isoformat()
    members_table = get_table("FamilyMembers")
    item = {
        "family_id": family_id,
        "user_id": user_id,
        "role": role,
        "joined_at": now,
    }
    members_table.put_item(Item=item)

    # Update user record with family_id
    users_table = get_table("Users")
    users_table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET family_id = :fid",
        ExpressionAttributeValues={":fid": family_id},
    )

    return item


def remove_member_from_family(family_id: str, user_id: str) -> None:
    """Remove a member from a family."""
    members_table = get_table("FamilyMembers")
    members_table.delete_item(
        Key={"family_id": family_id, "user_id": user_id},
    )

    # Remove family_id from user record
    users_table = get_table("Users")
    users_table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="REMOVE family_id",
    )
