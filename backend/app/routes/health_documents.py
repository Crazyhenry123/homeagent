"""Admin API routes for health document upload/download/management."""

from flask import Blueprint, g, jsonify, request

from app.auth import require_admin, require_auth
from app.services.health_documents import (
    create_document_metadata,
    delete_document,
    get_download_url,
    list_documents,
)

admin_health_documents_bp = Blueprint("admin_health_documents", __name__)


@admin_health_documents_bp.route("/health-documents/<user_id>", methods=["GET"])
@require_auth
@require_admin
def admin_list_documents(user_id: str):
    docs = list_documents(user_id)
    return jsonify({"documents": docs})


@admin_health_documents_bp.route("/health-documents/<user_id>/upload", methods=["POST"])
@require_auth
@require_admin
def admin_upload_document(user_id: str):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    filename = data.get("filename")
    content_type = data.get("content_type")
    file_size = data.get("file_size")

    if not filename or not content_type or file_size is None:
        return jsonify(
            {"error": "filename, content_type, and file_size are required"}
        ), 400

    try:
        doc = create_document_metadata(
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            file_size=int(file_size),
            uploaded_by=g.user_id,
            record_id=data.get("record_id"),
            description=data.get("description", ""),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(doc), 201


@admin_health_documents_bp.route(
    "/health-documents/<user_id>/<document_id>/download", methods=["GET"]
)
@require_auth
@require_admin
def admin_download_document(user_id: str, document_id: str):
    result = get_download_url(user_id, document_id)
    if not result:
        return jsonify({"error": "Document not found"}), 404
    return jsonify(result)


@admin_health_documents_bp.route(
    "/health-documents/<user_id>/<document_id>", methods=["DELETE"]
)
@require_auth
@require_admin
def admin_delete_document(user_id: str, document_id: str):
    deleted = delete_document(user_id, document_id)
    if not deleted:
        return jsonify({"error": "Document not found"}), 404
    return jsonify({"success": True})
