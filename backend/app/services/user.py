import secrets
import uuid
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key
from ulid import ULID

from app.models.dynamo import get_table
from app.services.profile import create_profile


def register_device(
    invite_code: str,
    device_name: str,
    platform: str,
    display_name: str,
) -> dict:
    """Redeem an invite code and register a new device.

    Returns dict with user_id and device_token.
    Raises ValueError if invite code is invalid.
    """
    codes_table = get_table("InviteCodes")

    # Fetch and validate invite code
    code_item = codes_table.get_item(Key={"code": invite_code}).get("Item")
    if not code_item:
        raise ValueError("Invalid invite code")
    if code_item["status"] != "active":
        raise ValueError("Invite code already used or expired")

    # Check if this is an admin invite
    is_admin = code_item.get("is_admin", False)

    # Create user
    user_id = str(ULID())
    users_table = get_table("Users")
    now = datetime.now(timezone.utc).isoformat()

    users_table.put_item(
        Item={
            "user_id": user_id,
            "name": display_name,
            "role": "admin" if is_admin else "member",
            "created_at": now,
        }
    )

    # Create device
    device_id = str(uuid.uuid4())
    device_token = secrets.token_urlsafe(48)
    devices_table = get_table("Devices")

    devices_table.put_item(
        Item={
            "device_id": device_id,
            "user_id": user_id,
            "device_token": device_token,
            "platform": platform,
            "device_name": device_name,
            "registered_at": now,
        }
    )

    # Create default member profile
    create_profile(
        user_id=user_id,
        display_name=display_name,
        role="admin" if is_admin else "member",
    )

    # Mark invite code as used
    codes_table.update_item(
        Key={"code": invite_code},
        UpdateExpression="SET #s = :used, used_by = :uid",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":used": "used", ":uid": user_id},
    )

    return {"user_id": user_id, "device_token": device_token}


def generate_invite_code(created_by: str) -> dict:
    """Generate a new invite code. Returns dict with code and expires_at."""
    code = secrets.token_hex(3).upper()[:6]
    expires_at = datetime(2099, 12, 31, tzinfo=timezone.utc).isoformat()

    codes_table = get_table("InviteCodes")
    codes_table.put_item(
        Item={
            "code": code,
            "created_by": created_by,
            "status": "active",
            "is_admin": False,
            "expires_at": expires_at,
        }
    )

    return {"code": code, "expires_at": expires_at}


def create_owner_user(
    email: str,
    display_name: str,
    cognito_sub: str,
) -> dict:
    """Create an owner user (family creator) in DynamoDB.

    Returns dict with user_id.
    Raises ValueError if email is already registered.
    """
    users_table = get_table("Users")

    # Check if email already exists
    result = users_table.query(
        IndexName="email-index",
        KeyConditionExpression=Key("email").eq(email),
        Limit=1,
    )
    if result.get("Items"):
        raise ValueError("An account with this email already exists")

    user_id = str(ULID())
    now = datetime.now(timezone.utc).isoformat()

    users_table.put_item(
        Item={
            "user_id": user_id,
            "name": display_name,
            "email": email,
            "cognito_sub": cognito_sub,
            "role": "owner",
            "created_at": now,
        }
    )

    # Create default member profile
    create_profile(
        user_id=user_id,
        display_name=display_name,
        role="owner",
    )

    return {"user_id": user_id}


def get_user_by_email(email: str) -> dict | None:
    """Look up a user by email using the email-index GSI."""
    users_table = get_table("Users")
    result = users_table.query(
        IndexName="email-index",
        KeyConditionExpression=Key("email").eq(email),
        Limit=1,
    )
    items = result.get("Items", [])
    return items[0] if items else None


def get_user_by_cognito_sub(cognito_sub: str) -> dict | None:
    """Look up a user by cognito_sub using the cognito_sub-index GSI."""
    users_table = get_table("Users")
    result = users_table.query(
        IndexName="cognito_sub-index",
        KeyConditionExpression=Key("cognito_sub").eq(cognito_sub),
        Limit=1,
    )
    items = result.get("Items", [])
    return items[0] if items else None


def delete_member(user_id: str) -> None:
    """Delete a member and all associated data across tables.

    Raises ValueError if user not found or user is an admin.
    """
    from app.services.conversation import delete_conversation
    from app.services.family_tree import delete_all_relationships

    # 1. Fetch user — reject if admin
    users_table = get_table("Users")
    user = users_table.get_item(Key={"user_id": user_id}).get("Item")
    if not user:
        raise ValueError("User not found")
    if user.get("role") == "admin":
        raise ValueError("Cannot delete an admin user")

    # 2. Delete Devices (query user_id-index GSI)
    devices_table = get_table("Devices")
    result = devices_table.query(
        IndexName="user_id-index",
        KeyConditionExpression=Key("user_id").eq(user_id),
        ProjectionExpression="device_id",
    )
    with devices_table.batch_writer() as batch:
        for item in result.get("Items", []):
            batch.delete_item(Key={"device_id": item["device_id"]})

    # 3. Delete Conversations + Messages
    convos_table = get_table("Conversations")
    result = convos_table.query(
        IndexName="user_conversations-index",
        KeyConditionExpression=Key("user_id").eq(user_id),
        ProjectionExpression="conversation_id",
    )
    for item in result.get("Items", []):
        delete_conversation(item["conversation_id"])

    # 4. Delete AgentConfigs
    configs_table = get_table("AgentConfigs")
    result = configs_table.query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        ProjectionExpression="user_id, agent_type",
    )
    with configs_table.batch_writer() as batch:
        for item in result.get("Items", []):
            batch.delete_item(
                Key={"user_id": item["user_id"], "agent_type": item["agent_type"]}
            )

    # 5. Delete FamilyRelationships (both directions)
    delete_all_relationships(user_id)

    # 5b. Delete HealthRecords, HealthObservations, and HealthDocuments
    from app.services.health_documents import delete_all_documents
    from app.services.health_observations import delete_all_observations
    from app.services.health_records import delete_all_health_records

    delete_all_health_records(user_id)
    delete_all_observations(user_id)
    delete_all_documents(user_id)

    # 6. Delete MemberProfile
    profiles_table = get_table("MemberProfiles")
    profiles_table.delete_item(Key={"user_id": user_id})

    # 7. Delete User record
    users_table.delete_item(Key={"user_id": user_id})
