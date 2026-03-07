"""Routes for chat media (image/audio) upload."""

from flask import Blueprint, g, jsonify, request

from app.auth import require_auth
from app.services.chat_media import create_upload, upload_file_to_s3

chat_media_bp = Blueprint("chat_media", __name__)


@chat_media_bp.route("/chat/upload-image", methods=["POST"])
@require_auth
def upload_image() -> tuple:
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


@chat_media_bp.route("/chat/upload", methods=["POST"])
@require_auth
def upload_media() -> tuple:
    """Upload a media file directly through the backend (no presigned URL).

    The client sends the file as multipart/form-data. The backend streams
    it to S3, avoiding the need for the client to reach S3/MinIO directly.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    content_type = file.content_type or request.form.get("content_type", "")
    if not content_type:
        return jsonify({"error": "content_type is required"}), 400

    # Read file data and check size
    file_data = file.read()
    file_size = len(file_data)
    if file_size == 0:
        return jsonify({"error": "Empty file"}), 400

    try:
        result = create_upload(
            user_id=g.user_id,
            content_type=content_type,
            file_size=file_size,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Upload the file to S3 directly
    try:
        upload_file_to_s3(result["media_id"], file_data, content_type)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to upload file to S3")
        return jsonify({"error": "Failed to upload file to storage"}), 500

    return jsonify({"media_id": result["media_id"]}), 201
