"""API routes for health records — self-access and admin CRUD.

Routes pass the request-scoped storage provider (if any) to service calls.
"""

from flask import Blueprint, g, jsonify, request

from app.auth import require_admin, require_auth
from app.services.health_audit import list_audit_log, list_user_audit_log
from app.services.health_records import (
    create_health_record,
    delete_health_record,
    get_health_record,
    get_health_summary,
    list_health_records,
    update_health_record,
)

health_records_bp = Blueprint("health_records", __name__)
admin_health_records_bp = Blueprint("admin_health_records", __name__)


def _get_storage():
    """Get storage provider from request context."""
    return getattr(g, "storage_provider", None)


# ── Self-access routes ──────────────────────────────────────────────


@health_records_bp.route("/health-records/me", methods=["GET"])
@require_auth
def get_my_health_records():
    record_type = request.args.get("record_type")
    records = list_health_records(
        g.user_id, record_type=record_type, storage=_get_storage()
    )
    return jsonify({"records": records})


@health_records_bp.route("/health-records/me/summary", methods=["GET"])
@require_auth
def get_my_health_summary():
    summary = get_health_summary(g.user_id, storage=_get_storage())
    return jsonify(summary)


# ── Admin routes ────────────────────────────────────────────────────


@admin_health_records_bp.route("/health-records/<user_id>", methods=["GET"])
@require_auth
@require_admin
def admin_list_health_records(user_id: str):
    record_type = request.args.get("record_type")
    records = list_health_records(
        user_id, record_type=record_type, storage=_get_storage()
    )
    return jsonify({"records": records})


@admin_health_records_bp.route("/health-records/<user_id>", methods=["POST"])
@require_auth
@require_admin
def admin_create_health_record(user_id: str):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    record_type = data.get("record_type")
    record_data = data.get("data")
    if not record_type or record_data is None:
        return jsonify({"error": "record_type and data are required"}), 400

    try:
        record = create_health_record(
            user_id=user_id,
            record_type=record_type,
            data=record_data,
            created_by=g.user_id,
            storage=_get_storage(),
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(record), 201


@admin_health_records_bp.route("/health-records/<user_id>/<record_id>", methods=["GET"])
@require_auth
@require_admin
def admin_get_health_record(user_id: str, record_id: str):
    record = get_health_record(user_id, record_id, storage=_get_storage())
    if not record:
        return jsonify({"error": "Record not found"}), 404
    return jsonify(record)


@admin_health_records_bp.route("/health-records/<user_id>/<record_id>", methods=["PUT"])
@require_auth
@require_admin
def admin_update_health_record(user_id: str, record_id: str):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    try:
        record = update_health_record(
            user_id, record_id, data, actor_id=g.user_id, storage=_get_storage()
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if not record:
        return jsonify({"error": "Record not found"}), 404
    return jsonify(record)


@admin_health_records_bp.route(
    "/health-records/<user_id>/<record_id>", methods=["DELETE"]
)
@require_auth
@require_admin
def admin_delete_health_record(user_id: str, record_id: str):
    deleted = delete_health_record(
        user_id, record_id, actor_id=g.user_id, storage=_get_storage()
    )
    if not deleted:
        return jsonify({"error": "Record not found"}), 404
    return jsonify({"success": True})


@admin_health_records_bp.route("/health-records/<user_id>/summary", methods=["GET"])
@require_auth
@require_admin
def admin_get_health_summary(user_id: str):
    summary = get_health_summary(user_id, storage=_get_storage())
    return jsonify(summary)


# ── Audit log routes ───────────────────────────────────────────────
# Audit logs always read from DynamoDB (never delegated to storage provider)


@admin_health_records_bp.route(
    "/health-records/<user_id>/<record_id>/audit", methods=["GET"]
)
@require_auth
@require_admin
def admin_get_record_audit_log(user_id: str, record_id: str):
    entries = list_audit_log(record_id)
    return jsonify({"audit_log": entries})


@admin_health_records_bp.route("/health-records/<user_id>/audit-log", methods=["GET"])
@require_auth
@require_admin
def admin_get_user_audit_log(user_id: str):
    entries = list_user_audit_log(user_id)
    return jsonify({"audit_log": entries})
