from flask import Blueprint, g, jsonify, request

from app.auth import require_admin, require_auth
from app.services.family import (
    create_family,
    get_family,
    get_family_by_owner,
    get_family_members,
    get_user_family_id,
)
from app.services.user import (
    cancel_invite_code,
    generate_invite_code,
    get_pending_invites_by_creator,
    register_device,
    send_invite_email,
)

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
    return jsonify(
        {
            "valid": True,
            "user_id": g.user_id,
            "name": g.user_name,
            "role": g.user_role,
        }
    )


admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/invite-codes", methods=["POST"])
@require_auth
@require_admin
def create_invite_code():
    result = generate_invite_code(created_by=g.user_id)
    return jsonify(result), 201


family_bp = Blueprint("family", __name__)


@family_bp.route("", methods=["POST"])
@require_auth
@require_admin
def create_family_route():
    """Create a new family. Only admin/owner can create."""
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "Family name is required"}), 400

    # Check if user already owns a family
    existing = get_family_by_owner(g.user_id)
    if existing:
        return jsonify({"error": "You already own a family"}), 409

    family = create_family(
        owner_user_id=g.user_id,
        family_name=data["name"],
    )
    return jsonify(family), 201


@family_bp.route("", methods=["GET"])
@require_auth
def get_family_info():
    """Get current family info + members list."""
    family_id = get_user_family_id(g.user_id)
    if not family_id:
        return jsonify({"error": "You are not in a family"}), 404

    family = get_family(family_id)
    if not family:
        return jsonify({"error": "Family not found"}), 404

    members = get_family_members(family_id)
    return jsonify(
        {
            "family": family,
            "members": members,
        }
    )


@family_bp.route("/invite", methods=["POST"])
@require_auth
@require_admin
def invite_member():
    """Owner invites a member by email. Creates invite code and sends email."""
    data = request.get_json()
    if not data or not data.get("email"):
        return jsonify({"error": "Email is required"}), 400

    email = data["email"].strip().lower()

    # Get the owner's family
    family = get_family_by_owner(g.user_id)
    if not family:
        return jsonify({"error": "You must create a family first"}), 400
    if family["owner_user_id"] != g.user_id:
        return jsonify({"error": "Only the family owner can invite members"}), 403

    family_id = family["family_id"]
    family_name = data.get("family_name") or family.get("name", "My Family")

    # Generate invite code linked to family
    invite = generate_invite_code(
        created_by=g.user_id,
        invited_email=email,
        family_id=family_id,
    )

    # Try to send email (gracefully degrades)
    email_sent = send_invite_email(
        email=email,
        invite_code=invite["code"],
        family_name=family_name,
        inviter_name=g.user_name,
    )

    return jsonify(
        {
            **invite,
            "email_sent": email_sent,
            "family_name": family_name,
        }
    ), 201


@family_bp.route("/invites", methods=["GET"])
@require_auth
@require_admin
def list_pending_invites():
    """List pending invites created by the current owner."""
    invites = get_pending_invites_by_creator(g.user_id)
    return jsonify({"invites": invites})


@family_bp.route("/invites/<code>", methods=["DELETE"])
@require_auth
@require_admin
def cancel_invite(code: str):
    """Cancel a pending invite code."""
    success = cancel_invite_code(code, g.user_id)
    if not success:
        return jsonify({"error": "Invite not found or not authorized"}), 404
    return jsonify({"status": "cancelled"})
