from functools import wraps
from typing import Callable

from flask import g, jsonify, request

from app.models.dynamo import get_table


def require_auth(f: Callable) -> Callable:
    """Middleware that validates device_token and attaches user info to g."""

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        device_token = auth_header[7:]
        if not device_token:
            return jsonify({"error": "Empty token"}), 401

        # Look up device by token
        devices_table = get_table("Devices")
        result = devices_table.query(
            IndexName="device_token-index",
            KeyConditionExpression="device_token = :token",
            ExpressionAttributeValues={":token": device_token},
            Limit=1,
        )

        items = result.get("Items", [])
        if not items:
            return jsonify({"error": "Invalid token"}), 401

        device = items[0]

        # Look up user
        users_table = get_table("Users")
        user = users_table.get_item(Key={"user_id": device["user_id"]}).get("Item")
        if not user:
            return jsonify({"error": "User not found"}), 401

        g.user_id = user["user_id"]
        g.user_name = user["name"]
        g.user_role = user.get("role", "member")
        g.device_id = device["device_id"]

        return f(*args, **kwargs)

    return decorated


def require_admin(f: Callable) -> Callable:
    """Middleware that requires admin role. Must be used after require_auth."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if g.get("user_role") != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)

    return decorated
