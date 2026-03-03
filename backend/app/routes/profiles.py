from flask import Blueprint, g, jsonify, request

from app.auth import require_admin, require_auth
from app.services.profile import get_profile, list_profiles, update_profile

profiles_bp = Blueprint("profiles", __name__)
admin_profiles_bp = Blueprint("admin_profiles", __name__)


@profiles_bp.route("/profiles/me", methods=["GET"])
@require_auth
def get_my_profile():
    profile = get_profile(g.user_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    return jsonify(profile)


@profiles_bp.route("/profiles/me", methods=["PUT"])
@require_auth
def update_my_profile():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    profile = update_profile(g.user_id, data)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
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


@admin_profiles_bp.route("/profiles", methods=["GET"])
@require_auth
@require_admin
def admin_list_profiles():
    profiles = list_profiles()
    return jsonify({"profiles": profiles})
