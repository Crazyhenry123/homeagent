import logging
import re

from flask import Blueprint, g, jsonify, request

from app.auth import require_admin, require_auth
from app.services.user import (
    create_owner_user,
    generate_invite_code,
    get_user_by_email,
    register_device,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

# Password validation: min 8 chars, uppercase, lowercase, number, special char
_PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^a-zA-Z\d]).{8,}$"
)


def _validate_email(email: str) -> bool:
    """Basic email format validation."""
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def _validate_password(password: str) -> str | None:
    """Validate password requirements. Returns error message or None."""
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not _PASSWORD_PATTERN.match(password):
        return (
            "Password must contain uppercase, lowercase, "
            "number, and special character"
        )
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
