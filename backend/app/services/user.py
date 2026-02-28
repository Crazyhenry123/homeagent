import secrets
import uuid
from datetime import datetime, timezone

from ulid import ULID

from app.models.dynamo import get_table


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
