import logging
import secrets
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from flask import current_app
from ulid import ULID

from app.models.dynamo import get_table
from app.services.agent_config import put_agent_config
from app.services.agent_template import get_default_agent_types
from app.services.profile import create_profile

logger = logging.getLogger(__name__)


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

    # Mark invite code as used immediately to prevent reuse
    user_id = str(ULID())
    codes_table.update_item(
        Key={"code": invite_code},
        UpdateExpression="SET #s = :used, used_by = :uid",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":used": "used", ":uid": user_id},
    )

    # Create user
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

    # Auto-enable default agents for new members
    for agent_type in get_default_agent_types():
        try:
            put_agent_config(user_id, agent_type, enabled=True)
        except ValueError:
            pass  # Template not yet seeded — skip gracefully

    # Auto-join family if invite code has a family_id
    family_id = code_item.get("family_id")
    if family_id:
        from app.services.family import add_member_to_family

        add_member_to_family(family_id, user_id, role="member")
    elif is_admin:
        # Auto-create family for admin/owner registration
        from app.services.family import create_family

        create_family(owner_user_id=user_id, family_name=f"{display_name}'s Family")

    return {"user_id": user_id, "device_token": device_token}


def generate_invite_code(
    created_by: str,
    invited_email: str | None = None,
    family_id: str | None = None,
) -> dict:
    """Generate a new invite code.

    Args:
        created_by: User ID of the creator.
        invited_email: Optional email of the invited person.
        family_id: Optional family ID to auto-join on registration.

    Returns dict with code, expires_at, and optional invited_email/family_id.
    """
    expires_at = datetime(2099, 12, 31, tzinfo=timezone.utc).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    codes_table = get_table("InviteCodes")

    for _ in range(5):
        code = secrets.token_hex(3).upper()[:6]

        item: dict = {
            "code": code,
            "created_by": created_by,
            "status": "active",
            "is_admin": False,
            "expires_at": expires_at,
            "created_at": now,
            "invite_type": "email" if invited_email else "code",
        }

        if invited_email:
            item["invited_email"] = invited_email
        if family_id:
            item["family_id"] = family_id

        try:
            codes_table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(code)",
            )
            result: dict = {"code": code, "expires_at": expires_at}
            if invited_email:
                result["invited_email"] = invited_email
            if family_id:
                result["family_id"] = family_id
            return result
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                continue
            raise

    raise RuntimeError("Failed to generate a unique invite code after 5 attempts")


def send_invite_email(
    email: str,
    invite_code: str,
    family_name: str,
    inviter_name: str,
) -> bool:
    """Send an invite email via AWS SES.

    Returns True if sent successfully, False if SES is disabled or sending fails.
    """
    ses_enabled = current_app.config.get("SES_ENABLED", False)
    from_email = current_app.config.get("SES_FROM_EMAIL", "")

    if not ses_enabled or not from_email:
        logger.info(
            "SES not enabled, skipping email to %s with code %s",
            email,
            invite_code,
        )
        return False

    subject = f"You're invited to join {family_name}!"
    body_text = (
        f"Hi!\n\n"
        f"{inviter_name} has invited you to join their family on HomeAgent.\n\n"
        f"Your invite code is: {invite_code}\n\n"
        f"Family: {family_name}\n\n"
        f"Open the HomeAgent app and enter this code to join.\n"
    )
    body_html = (
        f"<h2>You're invited to join {family_name}!</h2>"
        f"<p>{inviter_name} has invited you to join their family on HomeAgent.</p>"
        f"<p>Your invite code is: <strong>{invite_code}</strong></p>"
        f"<p>Family: {family_name}</p>"
        f"<p>Open the HomeAgent app and enter this code to join.</p>"
    )

    try:
        region = current_app.config.get("AWS_REGION", "us-east-1")
        ses_client = boto3.client("ses", region_name=region)
        ses_client.send_email(
            Source=from_email,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": body_text, "Charset": "UTF-8"},
                    "Html": {"Data": body_html, "Charset": "UTF-8"},
                },
            },
        )
        logger.info("Invite email sent to %s", email)
        return True
    except Exception:
        logger.exception("Failed to send invite email to %s", email)
        return False


def get_pending_invites_by_creator(created_by: str) -> list[dict]:
    """Get all active invite codes created by a user."""
    codes_table = get_table("InviteCodes")
    items = []
    last_key = None
    while True:
        kwargs = {
            "FilterExpression": Attr("created_by").eq(created_by) & Attr("status").eq("active"),
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key
        result = codes_table.scan(**kwargs)
        items.extend(result.get("Items", []))
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
    return items


def cancel_invite_code(code: str, user_id: str) -> bool:
    """Cancel a pending invite code. Only the creator can cancel.

    Returns True if cancelled, False if not found or not authorized.
    """
    codes_table = get_table("InviteCodes")
    item = codes_table.get_item(Key={"code": code}).get("Item")
    if not item:
        return False
    if item.get("created_by") != user_id:
        return False
    if item.get("status") != "active":
        return False

    codes_table.update_item(
        Key={"code": code},
        UpdateExpression="SET #s = :cancelled",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":cancelled": "cancelled"},
    )
    return True


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

    # Auto-create family for the owner
    from app.services.family import create_family

    create_family(owner_user_id=user_id, family_name=f"{display_name}'s Family")

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

    # 5b. Delete MemberPermissions
    from app.services.member_permissions import delete_all_permissions

    delete_all_permissions(user_id)

    # 5c. Delete HealthRecords, HealthObservations, and HealthDocuments
    from app.services.health_documents import delete_all_documents
    from app.services.health_observations import delete_all_observations
    from app.services.health_records import delete_all_health_records

    # Resolve user's storage provider so external data is also cleaned up
    storage = None
    try:
        from app.storage.provider_factory import get_storage_provider

        storage = get_storage_provider(user_id)
    except (ImportError, Exception):
        pass

    delete_all_health_records(user_id, storage=storage)
    delete_all_observations(user_id, storage=storage)
    delete_all_documents(user_id, storage=storage)

    # 6. Delete MemberProfile
    profiles_table = get_table("MemberProfiles")
    profiles_table.delete_item(Key={"user_id": user_id})

    # 7. Delete User record
    users_table.delete_item(Key={"user_id": user_id})
