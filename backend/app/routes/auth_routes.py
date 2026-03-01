from flask import Blueprint, g, jsonify, request

from app.auth import require_admin, require_auth
from app.services.user import generate_invite_code, register_device

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    required = ["invite_code", "device_name", "platform", "display_name"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    if data["platform"] not in ("ios", "android", "web"):
        return jsonify({"error": "platform must be 'ios', 'android', or 'web'"}), 400

    try:
        result = register_device(
            invite_code=data["invite_code"],
            device_name=data["device_name"],
            platform=data["platform"],
            display_name=data["display_name"],
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(result), 201


@auth_bp.route("/verify", methods=["POST"])
@require_auth
def verify():
    return jsonify({
        "valid": True,
        "user_id": g.user_id,
        "name": g.user_name,
        "role": g.user_role,
    })


admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/invite-codes", methods=["POST"])
@require_auth
@require_admin
def create_invite_code():
    result = generate_invite_code(created_by=g.user_id)
    return jsonify(result), 201
