"""Routes for member permission management.

Members can view/grant/revoke their own data access permissions.
"""

from flask import Blueprint, g, jsonify, request

from app.auth import require_auth
from app.services.agent_template import get_template_by_type, _BUILTIN_AGENTS
from app.services.member_permissions import (
    VALID_PERMISSION_TYPES,
    get_active_permissions,
    grant_permission,
    revoke_permission,
)

permission_bp = Blueprint("permissions", __name__)


@permission_bp.route("/permissions", methods=["GET"])
@require_auth
def get_my_permissions():
    """Get all active permissions for the authenticated user."""
    permissions = get_active_permissions(g.user_id)
    return jsonify({"permissions": permissions})


@permission_bp.route("/permissions/<permission_type>", methods=["PUT"])
@require_auth
def grant_my_permission(permission_type: str):
    """Grant or update a permission with configuration."""
    if permission_type not in VALID_PERMISSION_TYPES:
        return jsonify({"error": f"Invalid permission type: {permission_type}"}), 400

    data = request.get_json() or {}
    config = data.get("config", {})

    result = grant_permission(
        user_id=g.user_id,
        permission_type=permission_type,
        config=config,
        granted_by=g.user_id,
    )
    return jsonify(result)


@permission_bp.route("/permissions/<permission_type>", methods=["DELETE"])
@require_auth
def revoke_my_permission(permission_type: str):
    """Revoke a permission."""
    if permission_type not in VALID_PERMISSION_TYPES:
        return jsonify({"error": f"Invalid permission type: {permission_type}"}), 400

    revoked = revoke_permission(g.user_id, permission_type)
    if not revoked:
        return jsonify({"error": "Permission not found"}), 404

    return jsonify({"success": True})


@permission_bp.route("/permissions/required/<agent_type>", methods=["GET"])
@require_auth
def get_required_permissions(agent_type: str):
    """Get required permissions for an agent type."""
    # Check built-in agents first for quick lookup
    if agent_type in _BUILTIN_AGENTS:
        required = _BUILTIN_AGENTS[agent_type].get("required_permissions", [])
    else:
        template = get_template_by_type(agent_type)
        if not template:
            return jsonify({"error": f"Unknown agent type: {agent_type}"}), 404
        required = template.get("required_permissions", [])

    return jsonify({
        "agent_type": agent_type,
        "required_permissions": required,
    })
