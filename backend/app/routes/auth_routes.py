import logging
import re

from flask import Blueprint, g, jsonify, request

from app.auth import require_admin, require_auth
from app.services.family import (
    create_family,
    get_family,
    get_family_by_owner,
    get_family_members,
    get_family_settings,
    get_user_family_id,
    update_family_settings,
)
from app.services.user import (
    cancel_invite_code,
    create_owner_user,
    generate_invite_code,
    get_pending_invites_by_creator,
    get_user_by_email,
    register_device,
    send_invite_email,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

# Password validation: min 8 chars
_PASSWORD_MIN_LENGTH = 8


def _validate_email(email: str) -> bool:
    """Basic email format validation."""
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def _validate_password(password: str) -> str | None:
    """Validate password requirements. Returns error message or None."""
    if len(password) < _PASSWORD_MIN_LENGTH:
        return f"Password must be at least {_PASSWORD_MIN_LENGTH} characters"
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return "Password must contain at least one lowercase letter"
    if not re.search(r"[0-9]", password):
        return "Password must contain at least one number"
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Password must contain at least one special character"
    return None


@auth_bp.route("/register", methods=["POST"])
def register():
    """Register via invite code (existing member flow)."""
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


@auth_bp.route("/signup", methods=["POST"])
def signup():
    """Register a new family owner with email and password via Cognito."""
    from app.services.cognito import CognitoError, sign_up

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    required = ["email", "password", "display_name"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    email = data["email"].strip().lower()
    password = data["password"]
    display_name = data["display_name"].strip()

    if not _validate_email(email):
        return jsonify({"error": "Invalid email format"}), 400

    password_error = _validate_password(password)
    if password_error:
        return jsonify({"error": password_error}), 400

    if not display_name:
        return jsonify({"error": "Display name cannot be empty"}), 400

    # Pre-check: ensure email is not already registered in DynamoDB
    existing = get_user_by_email(email)
    if existing:
        return jsonify({"error": "An account with this email already exists", "code": "UsernameExistsException"}), 409

    try:
        cognito_sub = sign_up(email, password, display_name)
    except CognitoError as e:
        status = 409 if e.code == "UsernameExistsException" else 400
        return jsonify({"error": str(e), "code": e.code}), status

    # Create user in DynamoDB
    try:
        result = create_owner_user(
            email=email,
            display_name=display_name,
            cognito_sub=cognito_sub,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    return jsonify({"user_id": result["user_id"], "email": email}), 201


@auth_bp.route("/confirm", methods=["POST"])
def confirm():
    """Confirm email verification with code."""
    from app.services.cognito import CognitoError, confirm_sign_up

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    email = data.get("email", "").strip().lower()
    confirmation_code = data.get("confirmation_code", "").strip()

    if not email or not confirmation_code:
        return jsonify({"error": "Missing fields: email, confirmation_code"}), 400

    try:
        confirm_sign_up(email, confirmation_code)
    except CognitoError as e:
        return jsonify({"error": str(e), "code": e.code}), 400

    return jsonify({"confirmed": True}), 200


@auth_bp.route("/login", methods=["POST"])
def login():
    """Authenticate with email and password, return Cognito tokens + user info."""
    from app.services.cognito import CognitoError, sign_in

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Missing fields: email, password"}), 400

    try:
        tokens = sign_in(email, password)
    except CognitoError as e:
        status = 401 if e.code in (
            "NotAuthorizedException", "UserNotFoundException"
        ) else 400
        return jsonify({"error": str(e), "code": e.code}), status

    # Look up user info
    user = get_user_by_email(email)
    if not user:
        return jsonify({"error": "User not found in database"}), 404

    return jsonify({
        "tokens": {
            "id_token": tokens["id_token"],
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
        },
        "user": {
            "user_id": user["user_id"],
            "name": user["name"],
            "email": user.get("email", ""),
            "role": user.get("role", "member"),
        },
    }), 200


@auth_bp.route("/resend-code", methods=["POST"])
def resend_code():
    """Resend the email verification code."""
    from app.services.cognito import CognitoError, resend_confirmation_code

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    email = data.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "Missing field: email"}), 400

    try:
        resend_confirmation_code(email)
    except CognitoError as e:
        return jsonify({"error": str(e), "code": e.code}), 400

    return jsonify({"sent": True}), 200


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
    # Auto-attach the admin's family so new members join automatically
    family_id = get_user_family_id(g.user_id)
    result = generate_invite_code(created_by=g.user_id, family_id=family_id)
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


@family_bp.route("/settings", methods=["GET"])
@require_auth
def get_settings():
    """Get family settings."""
    family_id = get_user_family_id(g.user_id)
    if not family_id:
        return jsonify({"error": "You are not in a family"}), 404
    settings = get_family_settings(family_id)
    return jsonify({"settings": settings})


@family_bp.route("/settings", methods=["PUT"])
@require_auth
@require_admin
def update_settings():
    """Update family settings. Admin only."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    family_id = get_user_family_id(g.user_id)
    if not family_id:
        return jsonify({"error": "You are not in a family"}), 404

    try:
        settings = update_family_settings(family_id, data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"settings": settings})


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
