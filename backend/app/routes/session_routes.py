"""Session bootstrap endpoint — returns all user data in a single API call.

Replaces the need for 7 separate requests on app startup.
"""

import decimal
import logging
from typing import Any

from flask import Blueprint, Response, g, jsonify

from app.auth import require_auth
from app.models.dynamo import get_table
from app.services.agent_config import get_agent_configs, get_available_agent_types
from app.services.agent_template import get_available_templates
from app.services.conversation import list_conversations
from app.services.family import get_family, get_family_members, get_user_family_id
from app.services.member_permissions import get_active_permissions
from app.services.profile import get_profile

logger = logging.getLogger(__name__)

session_bp = Blueprint("session", __name__)


def _convert_decimals(obj: Any) -> Any:
    """Convert DynamoDB Decimal values to native Python types."""
    if isinstance(obj, list):
        return [_convert_decimals(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, decimal.Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    return obj


@session_bp.route("/session", methods=["GET"])
@require_auth
def get_session() -> tuple[Response, int] | Response:
    """Return all session data for the authenticated user in one call.

    Aggregates: user info, profile, family, agents, permissions, conversations.
    """
    user_id = g.user_id

    try:
        # 1. User info (from auth middleware + Users table for email)
        users_table = get_table("Users")
        user_record = users_table.get_item(Key={"user_id": user_id}).get("Item", {})
        user = {
            "user_id": user_id,
            "name": g.user_name,
            "email": user_record.get("email", ""),
            "role": g.user_role,
        }

        # 2. Profile
        profile = get_profile(user_id)

        # 3. Family (nullable — member may not belong to one)
        family_data = None
        try:
            family_id = get_user_family_id(user_id)
            if family_id:
                family_info = get_family(family_id)
                if family_info:
                    members = get_family_members(family_id)
                    family_data = {
                        "info": family_info,
                        "members": members,
                    }
        except Exception:
            logger.warning("Failed to load family data for user %s", user_id)

        # 4. Agents — available templates + user's configs + type definitions
        available = get_available_templates(user_id)
        configs = get_agent_configs(user_id)
        enabled_types = {
            c["agent_type"] for c in configs if c.get("enabled", False)
        }
        available_with_status = [
            {**t, "enabled": t["agent_type"] in enabled_types}
            for t in available
        ]

        # Include agent type definitions for admin screens
        agent_types = {}
        if g.user_role in ("admin", "owner"):
            agent_types = get_available_agent_types()

        # 5. Permissions
        permissions = get_active_permissions(user_id)

        # 6. Conversations (most recent 20)
        convos_result = list_conversations(user_id=user_id, limit=20)

        result = {
            "user": user,
            "profile": profile,
            "family": family_data,
            "agents": {
                "available": available_with_status,
                "my_configs": configs,
                "agent_types": agent_types,
            },
            "permissions": permissions,
            "conversations": {
                "items": convos_result.get("conversations", []),
                "next_cursor": convos_result.get("next_cursor"),
            },
        }

        return jsonify(_convert_decimals(result))
    except Exception:
        logger.exception("Session bootstrap failed for user %s", user_id)
        return jsonify({"error": "Failed to load session data"}), 500
