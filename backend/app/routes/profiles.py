from flask import Blueprint, g, jsonify, request

from app.auth import require_admin, require_auth
from app.services.profile import (
    create_profile,
    get_profile,
    list_profiles,
    update_profile,
)
from app.services.user import delete_member

profiles_bp = Blueprint("profiles", __name__)
admin_profiles_bp = Blueprint("admin_profiles", __name__)


def _ensure_profile() -> dict:
    """Get the current user's profile, auto-creating if missing (for pre-existing users)."""
    profile = get_profile(g.user_id)
    if not profile:
        profile = create_profile(g.user_id, g.user_name, g.user_role)
    return profile


@profiles_bp.route("/profiles/me", methods=["GET"])
@require_auth
def get_my_profile():
    return jsonify(_ensure_profile())


@profiles_bp.route("/profiles/me", methods=["PUT"])
@require_auth
def update_my_profile():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    _ensure_profile()
    profile = update_profile(g.user_id, data)
    return jsonify(profile)


@admin_profiles_bp.route("/profiles/<user_id>", methods=["GET"])
@require_auth
@require_admin
def admin_get_profile(user_id: str):
    profile = get_profile(user_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    return jsonify(profile)


@admin_profiles_bp.route("/profiles/<user_id>", methods=["PUT"])
@require_auth
@require_admin
def admin_update_profile(user_id: str):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    profile = update_profile(user_id, data)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    return jsonify(profile)


@admin_profiles_bp.route("/profiles/<user_id>", methods=["DELETE"])
@require_auth
@require_admin
def admin_delete_profile(user_id: str):
    if user_id == g.user_id:
        return jsonify({"error": "Cannot delete yourself"}), 400

    try:
        delete_member(user_id)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            return jsonify({"error": msg}), 404
        return jsonify({"error": msg}), 400

    return jsonify({"success": True})


@admin_profiles_bp.route("/profiles", methods=["GET"])
@require_auth
@require_admin
def admin_list_profiles():
    profiles = list_profiles()
    return jsonify({"profiles": profiles})
