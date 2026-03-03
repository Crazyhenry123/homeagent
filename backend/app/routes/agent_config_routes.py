from flask import Blueprint, jsonify, request

from app.auth import require_admin, require_auth
from app.services.agent_config import (
    delete_agent_config,
    get_agent_configs,
    get_available_agent_types,
    put_agent_config,
)

agent_config_bp = Blueprint("agent_config", __name__)


@agent_config_bp.route("/agents/types", methods=["GET"])
@require_auth
@require_admin
def list_agent_types():
    types = get_available_agent_types()

    # Ensure agent modules are imported so registry is populated
    try:
        import app.agents.health_advisor  # noqa: F401
    except ImportError:
        pass  # strands not installed (e.g., in test environment)
    from app.agents.registry import get_registered_types

    registered = get_registered_types()
    for type_key in types:
        types[type_key]["implemented"] = type_key in registered

    return jsonify({"agent_types": types})


@agent_config_bp.route("/agents/<user_id>", methods=["GET"])
@require_auth
@require_admin
def list_user_agents(user_id: str):
    configs = get_agent_configs(user_id)
    return jsonify({"agent_configs": configs})


@agent_config_bp.route("/agents/<user_id>/<agent_type>", methods=["PUT"])
@require_auth
@require_admin
def configure_agent(user_id: str, agent_type: str):
    data = request.get_json() or {}
    enabled = data.get("enabled", True)
    config = data.get("config")

    try:
        result = put_agent_config(user_id, agent_type, enabled=enabled, config=config)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(result)


@agent_config_bp.route("/agents/<user_id>/<agent_type>", methods=["DELETE"])
@require_auth
@require_admin
def remove_agent(user_id: str, agent_type: str):
    deleted = delete_agent_config(user_id, agent_type)
    if not deleted:
        return jsonify({"error": "Agent config not found"}), 404
    return jsonify({"success": True})
