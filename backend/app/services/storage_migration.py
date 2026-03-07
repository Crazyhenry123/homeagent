"""Service for migrating user data between storage providers."""
from __future__ import annotations

import io
import json
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from app.storage.base import StorageProvider

logger = logging.getLogger(__name__)

MIGRATED_COLLECTIONS = [
    "health_records",
    "health_observations",
    "health_documents_meta",
]


@dataclass
class MigrationProgress:
    status: str = "pending"  # pending, in_progress, completed, failed
    total_records: int = 0
    migrated_records: int = 0
    total_files: int = 0
    migrated_files: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict:
        progress_pct = 0
        total = self.total_records + self.total_files
        done = self.migrated_records + self.migrated_files
        if total > 0:
            progress_pct = int((done / total) * 100)
        return {
            "status": self.status,
            "progress": progress_pct,
            "total_records": self.total_records,
            "migrated_records": self.migrated_records,
            "total_files": self.total_files,
            "migrated_files": self.migrated_files,
            "errors": self.errors[:10],  # Limit error list
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class StorageMigrator:
    """Handles data migration between storage providers."""

    def __init__(self) -> None:
        self._progress: dict[str, MigrationProgress] = {}

    def get_progress(self, user_id: str) -> MigrationProgress | None:
        return self._progress.get(user_id)

    def migrate(
        self,
        user_id: str,
        source: StorageProvider,
        target: StorageProvider,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> MigrationProgress:
        """Migrate all user data from source to target provider.

        Steps:
        1. Count records and files
        2. Copy structured records collection by collection
        3. Copy files (health documents)
        4. Verify records in target
        5. Return result (does NOT delete from source)
        """
        progress = MigrationProgress(
            status="in_progress",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self._progress[user_id] = progress

        try:
            # Phase 1: Count
            for collection in MIGRATED_COLLECTIONS:
                records = source.query_records(user_id, collection)
                progress.total_records += len(records)

            # Count files (health documents with associated files)
            doc_records = source.query_records(user_id, "health_documents_meta")
            progress.total_files = len(doc_records)  # Each doc may have a file

            # Phase 2: Migrate structured records
            for collection in MIGRATED_COLLECTIONS:
                records = source.query_records(user_id, collection)
                for record in records:
                    try:
                        # Determine record ID field
                        record_id = self._get_record_id(collection, record)
                        target.put_record(user_id, collection, record_id, record)
                        progress.migrated_records += 1
                        if progress_callback:
                            progress_callback(
                                collection,
                                progress.migrated_records,
                                progress.total_records,
                            )
                    except Exception as e:
                        progress.errors.append(
                            f"Failed to migrate {collection}/{record.get('record_id', '?')}: {e}"
                        )
                        logger.warning("Migration error for %s: %s", collection, e)

            # Phase 3: Migrate files
            for doc in doc_records:
                try:
                    s3_key = doc.get("s3_key", "")
                    if s3_key:
                        file_data = source.get_file(user_id, s3_key)
                        if file_data:
                            data, content_type = file_data
                            target.put_file(user_id, s3_key, data, content_type)
                            progress.migrated_files += 1
                except Exception as e:
                    progress.errors.append(
                        f"Failed to migrate file {doc.get('document_id', '?')}: {e}"
                    )
                    logger.warning("File migration error: %s", e)

            # Phase 4: Verify (spot check)
            verification_ok = self._verify_migration(user_id, source, target)

            if not verification_ok:
                progress.errors.append(
                    "Verification failed: some records missing in target"
                )
                progress.status = "failed"
            else:
                progress.status = "completed"

        except Exception as e:
            progress.status = "failed"
            progress.errors.append(f"Migration failed: {e}")
            logger.exception("Migration failed for user %s", user_id)

        progress.completed_at = datetime.now(timezone.utc).isoformat()
        self._progress[user_id] = progress
        return progress

    def export_data(self, user_id: str, source: StorageProvider) -> bytes:
        """Export all user data as a ZIP archive.

        Archive structure:
            homeagent_export/
                health_records/
                    {record_id}.json
                health_observations/
                    {observation_id}.json
                health_documents_meta/
                    {document_id}.json
                health_documents_files/
                    {document_id}/{filename}
                manifest.json
        """
        buffer = io.BytesIO()
        manifest: dict = {
            "user_id": user_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "collections": {},
        }

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for collection in MIGRATED_COLLECTIONS:
                records = source.query_records(user_id, collection)
                manifest["collections"][collection] = len(records)
                for record in records:
                    record_id = self._get_record_id(collection, record)
                    path = f"homeagent_export/{collection}/{record_id}.json"
                    zf.writestr(path, json.dumps(record, default=str, indent=2))

            # Export document files
            doc_records = source.query_records(user_id, "health_documents_meta")
            file_count = 0
            for doc in doc_records:
                s3_key = doc.get("s3_key", "")
                if s3_key:
                    file_data = source.get_file(user_id, s3_key)
                    if file_data:
                        data, content_type = file_data
                        filename = doc.get("filename", "unknown")
                        doc_id = doc.get("document_id", "unknown")
                        path = f"homeagent_export/health_documents_files/{doc_id}/{filename}"
                        zf.writestr(path, data)
                        file_count += 1

            manifest["file_count"] = file_count
            zf.writestr(
                "homeagent_export/manifest.json",
                json.dumps(manifest, default=str, indent=2),
            )

        return buffer.getvalue()

    def import_data(
        self, user_id: str, target: StorageProvider, archive_data: bytes
    ) -> MigrationProgress:
        """Import user data from a ZIP archive."""
        progress = MigrationProgress(
            status="in_progress",
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        try:
            buffer = io.BytesIO(archive_data)
            with zipfile.ZipFile(buffer, "r") as zf:
                # Read manifest to validate archive structure
                try:
                    zf.read("homeagent_export/manifest.json")
                except KeyError:
                    progress.status = "failed"
                    progress.errors.append(
                        "Invalid archive: missing manifest.json"
                    )
                    progress.completed_at = datetime.now(timezone.utc).isoformat()
                    return progress

                for collection in MIGRATED_COLLECTIONS:
                    prefix = f"homeagent_export/{collection}/"
                    files = [
                        f
                        for f in zf.namelist()
                        if f.startswith(prefix) and f.endswith(".json")
                    ]
                    progress.total_records += len(files)

                    for filepath in files:
                        try:
                            data = json.loads(zf.read(filepath))
                            record_id = self._get_record_id(collection, data)
                            target.put_record(user_id, collection, record_id, data)
                            progress.migrated_records += 1
                        except Exception as e:
                            progress.errors.append(f"Import error {filepath}: {e}")

                # Import files
                file_prefix = "homeagent_export/health_documents_files/"
                file_entries = [
                    f
                    for f in zf.namelist()
                    if f.startswith(file_prefix) and not f.endswith("/")
                ]
                progress.total_files = len(file_entries)

                for filepath in file_entries:
                    try:
                        data = zf.read(filepath)
                        # Reconstruct s3_key from path
                        rel_path = filepath[len("homeagent_export/"):]
                        target.put_file(
                            user_id, rel_path, data, "application/octet-stream"
                        )
                        progress.migrated_files += 1
                    except Exception as e:
                        progress.errors.append(f"File import error {filepath}: {e}")

            progress.status = "completed"
        except Exception as e:
            progress.status = "failed"
            progress.errors.append(f"Import failed: {e}")
            logger.exception("Import failed for user %s", user_id)

        progress.completed_at = datetime.now(timezone.utc).isoformat()
        return progress

    def _get_record_id(self, collection: str, record: dict) -> str:
        """Extract the record ID field based on collection type."""
        if collection == "health_records":
            return record.get("record_id", "")
        elif collection == "health_observations":
            return record.get("observation_id", "")
        elif collection == "health_documents_meta":
            return record.get("document_id", "")
        return record.get("record_id", record.get("id", ""))

    def _verify_migration(
        self,
        user_id: str,
        source: StorageProvider,
        target: StorageProvider,
    ) -> bool:
        """Spot-check that migrated records exist in target."""
        for collection in MIGRATED_COLLECTIONS:
            source_records = source.query_records(user_id, collection)
            if not source_records:
                continue
            # Check first and last record
            for record in [source_records[0], source_records[-1]]:
                record_id = self._get_record_id(collection, record)
                target_record = target.get_record(user_id, collection, record_id)
                if target_record is None:
                    return False
        return True


# Singleton migrator instance
_migrator = StorageMigrator()


def get_migrator() -> StorageMigrator:
    return _migrator
