from flask import Blueprint, jsonify, request, g

from app.auth import require_admin, require_auth
from app.services.agent_template import (
    create_template,
    delete_template,
    list_templates,
    update_template,
)

agent_template_bp = Blueprint("agent_template", __name__)


@agent_template_bp.route("/agent-templates", methods=["GET"])
@require_auth
@require_admin
def list_all_templates():
    templates = list_templates()
    return jsonify({"templates": templates})


@agent_template_bp.route("/agent-templates", methods=["POST"])
@require_auth
@require_admin
def create_new_template():
    data = request.get_json() or {}

    required = ["name", "agent_type", "description", "system_prompt"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    try:
        template = create_template(
            name=data["name"],
            agent_type=data["agent_type"],
            description=data["description"],
            system_prompt=data["system_prompt"],
            default_config=data.get("default_config", {}),
            available_to=data.get("available_to", "all"),
            created_by=g.user_id,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(template), 201


@agent_template_bp.route("/agent-templates/<template_id>", methods=["PUT"])
@require_auth
@require_admin
def update_existing_template(template_id: str):
    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No update data provided"}), 400

    result = update_template(template_id, **data)
    if result is None:
        return jsonify({"error": "Template not found"}), 404

    return jsonify(result)


@agent_template_bp.route("/agent-templates/<template_id>", methods=["DELETE"])
@require_auth
@require_admin
def delete_existing_template(template_id: str):
    try:
        deleted = delete_template(template_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if not deleted:
        return jsonify({"error": "Template not found"}), 404

    return jsonify({"success": True})
