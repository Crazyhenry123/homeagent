"""Routes for memory sharing configuration."""

from flask import Blueprint, g, jsonify, request

from app.auth import require_auth
from app.services.family_memory import (
    get_family_shared_context,
    get_sharing_config,
    update_sharing_config,
)

memory_bp = Blueprint("memory", __name__)


@memory_bp.route("/memory/sharing", methods=["GET"])
@require_auth
def get_my_sharing_config():
    """Get the current user's memory sharing configuration."""
    config = get_sharing_config(g.user_id)
    return jsonify(config)


@memory_bp.route("/memory/sharing", methods=["PUT"])
@require_auth
def update_my_sharing_config():
    """Update the current user's memory sharing configuration."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    try:
        config = update_sharing_config(g.user_id, data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(config)


@memory_bp.route("/memory/family-context", methods=["GET"])
@require_auth
def preview_family_context():
    """Preview what family shared context the agent sees for the current user."""
    context = get_family_shared_context(g.user_id)
    return jsonify({"context": context})
