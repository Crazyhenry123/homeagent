"""Routes for chat media (image) upload."""

from flask import Blueprint, g, jsonify, request

from app.auth import require_auth
from app.services.chat_media import create_upload

chat_media_bp = Blueprint("chat_media", __name__)


@chat_media_bp.route("/chat/upload-image", methods=["POST"])
@require_auth
def upload_image():
    """Generate a presigned S3 URL for uploading a chat image."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    content_type = data.get("content_type")
    file_size = data.get("file_size")

    if not content_type or file_size is None:
        return jsonify({"error": "content_type and file_size are required"}), 400

    try:
        file_size = int(file_size)
    except (TypeError, ValueError):
        return jsonify({"error": "file_size must be an integer"}), 400

    try:
        result = create_upload(
            user_id=g.user_id,
            content_type=content_type,
            file_size=file_size,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(result), 201
