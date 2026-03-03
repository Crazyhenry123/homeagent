from flask import Blueprint, jsonify, request

from app.auth import require_admin, require_auth
from app.services.family_tree import (
    delete_relationship,
    get_family_tree,
    get_relationships,
    set_relationship,
)

family_tree_bp = Blueprint("family_tree", __name__)


@family_tree_bp.route("/family/relationships", methods=["GET"])
@require_auth
@require_admin
def list_all_relationships():
    relationships = get_family_tree()
    return jsonify({"relationships": relationships})


@family_tree_bp.route("/family/relationships/<user_id>", methods=["GET"])
@require_auth
@require_admin
def list_user_relationships(user_id: str):
    relationships = get_relationships(user_id)
    return jsonify({"relationships": relationships})


@family_tree_bp.route("/family/relationships", methods=["POST"])
@require_auth
@require_admin
def create_relationship():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    user_id = data.get("user_id")
    related_user_id = data.get("related_user_id")
    relationship_type = data.get("relationship_type")

    if not all([user_id, related_user_id, relationship_type]):
        return (
            jsonify(
                {"error": "user_id, related_user_id, and relationship_type are required"}
            ),
            400,
        )

    try:
        item = set_relationship(user_id, related_user_id, relationship_type)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(item), 201


@family_tree_bp.route(
    "/family/relationships/<user_id>/<related_user_id>", methods=["DELETE"]
)
@require_auth
@require_admin
def remove_relationship(user_id: str, related_user_id: str):
    delete_relationship(user_id, related_user_id)
    return jsonify({"success": True})
