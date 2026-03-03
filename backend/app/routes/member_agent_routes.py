from flask import Blueprint, jsonify, g

from app.auth import require_auth
from app.services.agent_config import (
    delete_agent_config,
    get_agent_configs,
    put_agent_config,
)
from app.services.agent_template import get_available_templates, get_template_by_type

member_agent_bp = Blueprint("member_agent", __name__)


@member_agent_bp.route("/agents/available", methods=["GET"])
@require_auth
def list_available_agents():
    """List templates available to the calling member, with enabled status."""
    user_id = g.user_id
    templates = get_available_templates(user_id)
    configs = get_agent_configs(user_id)

    enabled_types = {
        c["agent_type"] for c in configs if c.get("enabled", False)
    }

    result = []
    for t in templates:
        result.append({
            **t,
            "enabled": t["agent_type"] in enabled_types,
        })

    return jsonify({"agents": result})


@member_agent_bp.route("/agents/my", methods=["GET"])
@require_auth
def list_my_agents():
    """Return the member's current agent configs."""
    configs = get_agent_configs(g.user_id)
    return jsonify({"agent_configs": configs})


@member_agent_bp.route("/agents/my/<agent_type>", methods=["PUT"])
@require_auth
def enable_my_agent(agent_type: str):
    """Member enables an agent for themselves."""
    user_id = g.user_id

    # Validate template exists
    template = get_template_by_type(agent_type)
    if not template:
        return jsonify({"error": f"Unknown agent type: {agent_type}"}), 400

    # Validate agent is available to this member
    avail = template.get("available_to", "all")
    if avail != "all" and (not isinstance(avail, list) or user_id not in avail):
        return jsonify({"error": "This agent is not available to you"}), 403

    result = put_agent_config(user_id, agent_type, enabled=True)
    return jsonify(result)


@member_agent_bp.route("/agents/my/<agent_type>", methods=["DELETE"])
@require_auth
def disable_my_agent(agent_type: str):
    """Member disables one of their agents."""
    deleted = delete_agent_config(g.user_id, agent_type)
    if not deleted:
        return jsonify({"error": "Agent config not found"}), 404
    return jsonify({"success": True})
