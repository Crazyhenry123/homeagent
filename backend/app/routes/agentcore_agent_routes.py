"""AgentCore-migrated agent management endpoints.

Wires Flask routes to AgentManagementClient and the integration module's
add_sub_agent_for_user / remove_sub_agent_for_user functions.

Requirements: 4.1, 4.3, 4.4, 5.1, 5.2, 5.3, 6.3, 7.1, 7.2, 7.3
"""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.config import Config
from app.services.agent_management import AgentManagementClient
from app.services.agentcore_gateway import AgentCoreGatewayManager
from app.services.agentcore_integration import (
    add_sub_agent_for_user,
    remove_sub_agent_for_user,
)

agentcore_agents_bp = Blueprint("agentcore_agents", __name__)


def _get_mgmt() -> AgentManagementClient:
    cfg = Config()
    return AgentManagementClient(region=cfg.AWS_REGION)


def _get_gateway() -> AgentCoreGatewayManager:
    cfg = Config()
    return AgentCoreGatewayManager(region=cfg.AWS_REGION)


# ---------------------------------------------------------------------------
# Sub-agent config endpoints (wired to integration module)
# ---------------------------------------------------------------------------


@agentcore_agents_bp.route("/agents/configs", methods=["POST"])
def add_agent_config():
    """Add a sub-agent to a user's personal agent.

    Wires to add_sub_agent_for_user().
    Requires AgentCore Identity auth (g.user_id, g.user_role set by middleware).
    """
    if not hasattr(g, "user_id") or not g.user_id:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json() or {}
    agent_type = data.get("agent_type")
    if not agent_type:
        return jsonify({"error": "agent_type is required"}), 400

    config = data.get("config")
    target_user_id = data.get("user_id", g.user_id)

    try:
        agent_config = add_sub_agent_for_user(
            agent_mgmt=_get_mgmt(),
            gateway=_get_gateway(),
            user_id=target_user_id,
            agent_type=agent_type,
            config=config,
            requesting_user_id=g.user_id,
            requesting_user_role=getattr(g, "user_role", "member"),
        )
        return jsonify({
            "user_id": agent_config.user_id,
            "agent_type": agent_config.agent_type,
            "enabled": agent_config.enabled,
            "config": agent_config.config,
            "gateway_tool_id": agent_config.gateway_tool_id,
            "updated_at": agent_config.updated_at,
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403


@agentcore_agents_bp.route("/agents/configs/<agent_type>", methods=["DELETE"])
def remove_agent_config(agent_type: str):
    """Remove a sub-agent from a user's personal agent.

    Wires to remove_sub_agent_for_user().
    """
    if not hasattr(g, "user_id") or not g.user_id:
        return jsonify({"error": "Authentication required"}), 401

    target_user_id = request.args.get("user_id", g.user_id)

    try:
        deleted = remove_sub_agent_for_user(
            agent_mgmt=_get_mgmt(),
            user_id=target_user_id,
            agent_type=agent_type,
            requesting_user_id=g.user_id,
            requesting_user_role=getattr(g, "user_role", "member"),
        )
        if deleted:
            return jsonify({"status": "deleted"}), 200
        return jsonify({"error": "Config not found"}), 404
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403


# ---------------------------------------------------------------------------
# Template authorization endpoint
# ---------------------------------------------------------------------------


@agentcore_agents_bp.route(
    "/agents/templates/<template_id>/authorize", methods=["PUT"]
)
def authorize_members(template_id: str):
    """Authorize specific members to access a sub-agent template.

    Requires admin role.
    """
    if not hasattr(g, "user_id") or not g.user_id:
        return jsonify({"error": "Authentication required"}), 401

    if getattr(g, "user_role", "member") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    data = request.get_json() or {}
    member_ids = data.get("member_ids")
    if member_ids is None:
        return jsonify({"error": "member_ids is required"}), 400

    mgmt = _get_mgmt()
    template = mgmt.update_template(template_id, available_to=member_ids)
    if template is None:
        return jsonify({"error": "Template not found"}), 404

    return jsonify({
        "template_id": template.template_id,
        "agent_type": template.agent_type,
        "available_to": template.available_to,
    }), 200


# ---------------------------------------------------------------------------
# Available templates endpoint
# ---------------------------------------------------------------------------


@agentcore_agents_bp.route("/agents/available", methods=["GET"])
def list_available_agents():
    """List agent templates available to the current user."""
    if not hasattr(g, "user_id") or not g.user_id:
        return jsonify({"error": "Authentication required"}), 401

    mgmt = _get_mgmt()
    templates = mgmt.get_available_templates(g.user_id)
    return jsonify({
        "templates": [
            {
                "template_id": t.template_id,
                "agent_type": t.agent_type,
                "name": t.name,
                "description": t.description,
                "is_builtin": t.is_builtin,
            }
            for t in templates
        ]
    }), 200


# ---------------------------------------------------------------------------
# Template CRUD endpoints (wired to AgentManagementClient)
# ---------------------------------------------------------------------------


@agentcore_agents_bp.route("/agents/templates", methods=["GET"])
def list_templates():
    """List all templates (admin) or available templates (member)."""
    if not hasattr(g, "user_id") or not g.user_id:
        return jsonify({"error": "Authentication required"}), 401

    mgmt = _get_mgmt()
    if getattr(g, "user_role", "member") == "admin":
        templates = mgmt.list_templates()
    else:
        templates = mgmt.get_available_templates(g.user_id)

    return jsonify({
        "templates": [
            {
                "template_id": t.template_id,
                "agent_type": t.agent_type,
                "name": t.name,
                "description": t.description,
                "is_builtin": t.is_builtin,
                "available_to": t.available_to,
            }
            for t in templates
        ]
    }), 200


@agentcore_agents_bp.route("/agents/templates", methods=["POST"])
def create_template():
    """Create a new agent template. Requires admin role."""
    if not hasattr(g, "user_id") or not g.user_id:
        return jsonify({"error": "Authentication required"}), 401

    if getattr(g, "user_role", "member") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    data = request.get_json() or {}
    required = ["name", "agent_type", "description", "system_prompt"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    mgmt = _get_mgmt()
    try:
        template = mgmt.create_agent_template(
            name=data["name"],
            agent_type=data["agent_type"],
            description=data["description"],
            system_prompt=data["system_prompt"],
            tool_server_ids=data.get("tool_server_ids", []),
            default_config=data.get("default_config", {}),
            available_to=data.get("available_to", "all"),
            created_by=g.user_id,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "template_id": template.template_id,
        "agent_type": template.agent_type,
        "name": template.name,
    }), 201


@agentcore_agents_bp.route("/agents/templates/<template_id>", methods=["PUT"])
def update_template(template_id: str):
    """Update an agent template. Requires admin role."""
    if not hasattr(g, "user_id") or not g.user_id:
        return jsonify({"error": "Authentication required"}), 401

    if getattr(g, "user_role", "member") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No update data provided"}), 400

    mgmt = _get_mgmt()
    try:
        template = mgmt.update_template(template_id, **data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if template is None:
        return jsonify({"error": "Template not found"}), 404

    return jsonify({
        "template_id": template.template_id,
        "agent_type": template.agent_type,
        "name": template.name,
    }), 200


@agentcore_agents_bp.route("/agents/templates/<template_id>", methods=["DELETE"])
def delete_template(template_id: str):
    """Delete an agent template. Requires admin role."""
    if not hasattr(g, "user_id") or not g.user_id:
        return jsonify({"error": "Authentication required"}), 401

    if getattr(g, "user_role", "member") != "admin":
        return jsonify({"error": "Admin access required"}), 403

    mgmt = _get_mgmt()
    try:
        deleted = mgmt.delete_template(template_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if not deleted:
        return jsonify({"error": "Template not found"}), 404

    return jsonify({"success": True}), 200
