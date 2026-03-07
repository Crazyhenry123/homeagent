"""REST API routes for storage data migration."""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from flask import Blueprint, Response, g, jsonify, request

from app.auth import require_auth

if TYPE_CHECKING:
    from app.storage.base import StorageProvider

logger = logging.getLogger(__name__)

storage_migration_bp = Blueprint("storage_migration", __name__)


@storage_migration_bp.route("/storage/migrate", methods=["POST"])
@require_auth
def start_migration() -> tuple[Response, int] | Response:
    """Start async data migration to a new storage provider.

    Body: {"target_provider": "google_drive"}

    Pre-conditions:
    - Target provider must be connected (OAuth tokens exist)
    - No migration currently in progress
    """
    body = request.get_json(silent=True) or {}
    target_provider_type = body.get("target_provider")

    if not target_provider_type:
        return jsonify({"error": "target_provider is required"}), 400

    user_id = g.user_id

    # Check no migration in progress
    from app.services.storage_migration import get_migrator

    migrator = get_migrator()
    current = migrator.get_progress(user_id)
    if current and current.status == "in_progress":
        return jsonify({"error": "Migration already in progress"}), 409

    # Get source and target providers (validate before changing status)
    try:
        from app.storage.provider_factory import get_storage_provider

        source = get_storage_provider(user_id)

        # Create target provider
        from app.storage.box_provider import BoxProvider
        from app.storage.dropbox_provider import DropboxProvider
        from app.storage.google_drive_provider import GoogleDriveProvider
        from app.storage.local_provider import LocalProvider
        from app.storage.onedrive_provider import OneDriveProvider

        provider_map: dict[str, type] = {
            "local": LocalProvider,
            "google_drive": GoogleDriveProvider,
            "onedrive": OneDriveProvider,
            "dropbox": DropboxProvider,
            "box": BoxProvider,
        }

        target_cls = provider_map.get(target_provider_type)
        if not target_cls:
            return jsonify({"error": f"Unknown provider: {target_provider_type}"}), 400
        target = target_cls(user_id)

    except ImportError:
        logger.warning("Storage providers not available yet")
        return jsonify(
            {
                "migration_id": user_id,
                "status": "pending",
                "message": (
                    "Storage provider module not yet available. "
                    "Migration will be available after the storage abstraction is deployed."
                ),
            }
        ), 202

    # Update storage config status to "migrating" (after provider validation)
    try:
        from app.services.storage_config import update_storage_status

        update_storage_status(user_id, "migrating")
    except ImportError:
        pass

    # Run migration in background thread
    def run_migration() -> None:
        try:
            result = migrator.migrate(user_id, source, target)
            if result.status == "completed":
                try:
                    from app.services.storage_config import set_storage_config

                    set_storage_config(user_id, target_provider_type)
                except ImportError:
                    pass
            else:
                try:
                    from app.services.storage_config import update_storage_status

                    update_storage_status(user_id, "error")
                except ImportError:
                    pass
                except Exception:
                    logger.warning("Failed to update storage status to error", exc_info=True)
        except Exception:
            logger.exception("Background migration failed for user %s", user_id)
            try:
                from app.services.storage_config import update_storage_status

                update_storage_status(user_id, "error")
            except ImportError:
                pass
            except Exception:
                logger.warning("Failed to update storage status after failure", exc_info=True)

    thread = threading.Thread(target=run_migration, daemon=True)
    thread.start()

    return jsonify(
        {
            "migration_id": user_id,
            "status": "started",
        }
    ), 202


@storage_migration_bp.route("/storage/migrate/status", methods=["GET"])
@require_auth
def migration_status() -> tuple[Response, int] | Response:
    """Get current migration status."""
    from app.services.storage_migration import get_migrator

    migrator = get_migrator()
    progress = migrator.get_progress(g.user_id)

    if not progress:
        return jsonify({"status": "none", "message": "No migration in progress or completed"})

    return jsonify(progress.to_dict())


@storage_migration_bp.route("/storage/export", methods=["POST"])
@require_auth
def export_data() -> tuple[Response, int] | Response:
    """Export all user's health data as a ZIP archive.

    Returns the ZIP file directly as a download.
    """
    from app.services.storage_migration import get_migrator

    try:
        # Get current provider
        try:
            from app.storage.provider_factory import get_storage_provider

            source = get_storage_provider(g.user_id)
        except ImportError:
            # Fallback: use local provider directly
            from app.storage.local_provider import LocalProvider

            source = LocalProvider()

        migrator = get_migrator()
        archive = migrator.export_data(g.user_id, source)

        return Response(
            archive,
            mimetype="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=homeagent_export_{g.user_id[:8]}.zip",
                "Content-Length": str(len(archive)),
            },
        )
    except ImportError:
        return jsonify(
            {
                "error": "Export not available yet. Storage module not deployed.",
            }
        ), 503
    except Exception:
        logger.exception("Export failed for user %s", g.user_id)
        return jsonify({"error": "Export failed"}), 500


@storage_migration_bp.route("/storage/import", methods=["POST"])
@require_auth
def import_data() -> tuple[Response, int] | Response:
    """Import user data from an uploaded ZIP archive.

    Expects multipart form data with a 'file' field.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.endswith(".zip"):
        return jsonify({"error": "File must be a ZIP archive"}), 400

    # 50MB limit for imports
    max_size = 50 * 1024 * 1024
    archive_data = file.read()
    if len(archive_data) > max_size:
        return jsonify(
            {"error": f"File too large. Maximum size: {max_size // (1024 * 1024)}MB"}
        ), 413

    try:
        from app.storage.provider_factory import get_storage_provider

        target = get_storage_provider(g.user_id)
    except ImportError:
        try:
            from app.storage.local_provider import LocalProvider

            target = LocalProvider()
        except ImportError:
            return jsonify({"error": "Storage module not available"}), 503

    from app.services.storage_migration import get_migrator

    migrator = get_migrator()

    result = migrator.import_data(g.user_id, target, archive_data)

    status_code = 200 if result.status == "completed" else 500
    return jsonify(result.to_dict()), status_code
