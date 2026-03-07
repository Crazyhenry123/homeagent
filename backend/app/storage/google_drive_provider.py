"""Google Drive storage provider implementation."""

from __future__ import annotations

import io
import json
import logging
from typing import Any

from app.storage.base import StorageProvider
from app.storage.token_manager import OAuthTokenManager

logger = logging.getLogger(__name__)

_ROOT_FOLDER = "HomeAgent"


class GoogleDriveProvider(StorageProvider):
    """Store user data as JSON files in Google Drive.

    Folder structure::

        HomeAgent/
            {collection}/
                {record_id}.json
    """

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id
        self._token_manager = OAuthTokenManager(user_id)
        self._folder_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_service(self) -> Any | None:
        """Build an authorized Google Drive service object."""
        try:
            from google.oauth2.credentials import Credentials  # noqa: WPS433
            from googleapiclient.discovery import build  # noqa: WPS433

            token = self._token_manager.get_valid_token("google_drive")
            if not token:
                logger.error("No valid Google Drive token for user=%s", self._user_id)
                return None

            creds = Credentials(token=token)
            return build("drive", "v3", credentials=creds)
        except Exception:
            logger.exception("Failed to build Google Drive service")
            return None

    def _find_or_create_folder(
        self, service: Any, name: str, parent_id: str | None = None
    ) -> str | None:
        """Find a folder by name (under *parent_id*) or create it."""
        cache_key = f"{parent_id or 'root'}:{name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        try:
            query = (
                f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
                f"and trashed=false"
            )
            if parent_id:
                query += f" and '{parent_id}' in parents"

            results = (
                service.files()
                .list(q=query, spaces="drive", fields="files(id, name)")
                .execute()
            )
            files = results.get("files", [])
            if files:
                folder_id = files[0]["id"]
                self._folder_cache[cache_key] = folder_id
                return folder_id

            # Create the folder
            metadata: dict[str, Any] = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
            }
            if parent_id:
                metadata["parents"] = [parent_id]
            folder = service.files().create(body=metadata, fields="id").execute()
            folder_id = folder["id"]
            self._folder_cache[cache_key] = folder_id
            return folder_id
        except Exception:
            logger.exception("Failed to find/create folder %s", name)
            return None

    def _get_collection_folder(self, service: Any, collection: str) -> str | None:
        """Return the folder ID for HomeAgent/{collection}."""
        root_id = self._find_or_create_folder(service, _ROOT_FOLDER)
        if not root_id:
            return None
        return self._find_or_create_folder(service, collection, parent_id=root_id)

    def _find_file(
        self, service: Any, folder_id: str, filename: str
    ) -> str | None:
        """Find a file by name inside *folder_id*."""
        try:
            query = (
                f"name='{filename}' and '{folder_id}' in parents and trashed=false"
            )
            results = (
                service.files()
                .list(q=query, spaces="drive", fields="files(id)")
                .execute()
            )
            files = results.get("files", [])
            return files[0]["id"] if files else None
        except Exception:
            logger.exception("Failed to find file %s", filename)
            return None

    def _record_key_to_filename(self, key: dict[str, str]) -> str:
        """Derive a deterministic filename from a record key."""
        parts = sorted(key.values())
        return "_".join(parts) + ".json"

    # ------------------------------------------------------------------
    # Record operations
    # ------------------------------------------------------------------

    def put_record(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        condition_expression: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            from googleapiclient.http import MediaIoBaseUpload  # noqa: WPS433

            service = self._get_service()
            if not service:
                return None

            folder_id = self._get_collection_folder(service, collection)
            if not folder_id:
                return None

            filename = self._record_key_to_filename(
                {k: v for k, v in record.items() if isinstance(v, str)}
            )
            # Check for existing file to update
            existing_id = self._find_file(service, folder_id, filename)

            data = json.dumps(record, default=str).encode("utf-8")
            media = MediaIoBaseUpload(
                io.BytesIO(data), mimetype="application/json", resumable=False
            )

            if existing_id:
                service.files().update(
                    fileId=existing_id, media_body=media
                ).execute()
            else:
                metadata = {"name": filename, "parents": [folder_id]}
                service.files().create(
                    body=metadata, media_body=media, fields="id"
                ).execute()
            return record
        except Exception:
            logger.exception("put_record failed for %s", collection)
            return None

    def get_record(
        self,
        collection: str,
        key: dict[str, str],
    ) -> dict[str, Any] | None:
        try:
            service = self._get_service()
            if not service:
                return None

            folder_id = self._get_collection_folder(service, collection)
            if not folder_id:
                return None

            filename = self._record_key_to_filename(key)
            file_id = self._find_file(service, folder_id, filename)
            if not file_id:
                return None

            content = service.files().get_media(fileId=file_id).execute()
            return json.loads(content)
        except Exception:
            logger.exception("get_record failed for %s", collection)
            return None

    def query_records(
        self,
        collection: str,
        key_condition: dict[str, Any],
        *,
        index_name: str | None = None,
        filter_expression: dict[str, Any] | None = None,
        limit: int | None = None,
        scan_forward: bool = True,
    ) -> list[dict[str, Any]]:
        try:
            service = self._get_service()
            if not service:
                return []

            folder_id = self._get_collection_folder(service, collection)
            if not folder_id:
                return []

            # List all JSON files in the collection folder
            query = f"'{folder_id}' in parents and trashed=false and mimeType='application/json'"
            results = (
                service.files()
                .list(q=query, spaces="drive", fields="files(id, name)")
                .execute()
            )
            files = results.get("files", [])

            records: list[dict[str, Any]] = []
            for f in files:
                content = service.files().get_media(fileId=f["id"]).execute()
                record = json.loads(content)

                # Apply key_condition filter
                match = True
                for attr, value in key_condition.items():
                    if isinstance(value, tuple):
                        op, val = value
                        rec_val = record.get(attr, "")
                        if op == "begins_with" and not str(rec_val).startswith(
                            str(val)
                        ):
                            match = False
                        elif op == "eq" and rec_val != val:
                            match = False
                    else:
                        if record.get(attr) != value:
                            match = False
                if not match:
                    continue

                # Apply filter_expression
                if filter_expression:
                    for attr, value in filter_expression.items():
                        if isinstance(value, tuple):
                            op, val = value
                            if op == "eq" and record.get(attr) != val:
                                match = False
                            elif op == "ne" and record.get(attr) == val:
                                match = False
                            elif op == "contains" and str(val) not in str(
                                record.get(attr, "")
                            ):
                                match = False
                        else:
                            if record.get(attr) != value:
                                match = False
                if match:
                    records.append(record)

            # Sort by the sort key if available
            if key_condition:
                sk = list(key_condition.keys())[-1]
                records.sort(
                    key=lambda r: str(r.get(sk, "")), reverse=not scan_forward
                )

            if limit:
                records = records[:limit]

            return records
        except Exception:
            logger.exception("query_records failed for %s", collection)
            return []

    def update_record(
        self,
        collection: str,
        key: dict[str, str],
        updates: dict[str, Any],
        *,
        condition_expression: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            record = self.get_record(collection, key)
            if record is None:
                return None
            record.update(updates)
            return self.put_record(collection, record)
        except Exception:
            logger.exception("update_record failed for %s", collection)
            return None

    def delete_record(
        self,
        collection: str,
        key: dict[str, str],
    ) -> bool:
        try:
            service = self._get_service()
            if not service:
                return False

            folder_id = self._get_collection_folder(service, collection)
            if not folder_id:
                return False

            filename = self._record_key_to_filename(key)
            file_id = self._find_file(service, folder_id, filename)
            if not file_id:
                return False

            service.files().delete(fileId=file_id).execute()
            return True
        except Exception:
            logger.exception("delete_record failed for %s", collection)
            return False

    def delete_all_records(
        self,
        collection: str,
        partition_key: dict[str, str],
    ) -> int:
        try:
            service = self._get_service()
            if not service:
                return 0

            folder_id = self._get_collection_folder(service, collection)
            if not folder_id:
                return 0

            query = f"'{folder_id}' in parents and trashed=false"
            results = (
                service.files()
                .list(q=query, spaces="drive", fields="files(id, name)")
                .execute()
            )
            files = results.get("files", [])

            pk_value = list(partition_key.values())[0]
            count = 0
            for f in files:
                # Check if file belongs to the partition
                try:
                    content = service.files().get_media(fileId=f["id"]).execute()
                    record = json.loads(content)
                    pk_attr = list(partition_key.keys())[0]
                    if record.get(pk_attr) == pk_value:
                        service.files().delete(fileId=f["id"]).execute()
                        count += 1
                except Exception:
                    continue
            return count
        except Exception:
            logger.exception("delete_all_records failed for %s", collection)
            return 0

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def put_file(
        self,
        path: str,
        data: bytes,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str | None:
        try:
            from googleapiclient.http import MediaIoBaseUpload  # noqa: WPS433

            service = self._get_service()
            if not service:
                return None

            # Parse path into folder/filename
            parts = path.rsplit("/", 1)
            if len(parts) == 2:
                folder_path, filename = parts
            else:
                folder_path, filename = "", parts[0]

            # Navigate/create folder hierarchy under HomeAgent
            root_id = self._find_or_create_folder(service, _ROOT_FOLDER)
            parent_id = root_id
            if folder_path:
                for segment in folder_path.split("/"):
                    parent_id = self._find_or_create_folder(
                        service, segment, parent_id=parent_id
                    )
                    if not parent_id:
                        return None

            media = MediaIoBaseUpload(
                io.BytesIO(data),
                mimetype=content_type or "application/octet-stream",
                resumable=False,
            )

            existing_id = self._find_file(service, parent_id, filename)
            if existing_id:
                service.files().update(
                    fileId=existing_id, media_body=media
                ).execute()
            else:
                file_metadata: dict[str, Any] = {
                    "name": filename,
                    "parents": [parent_id],
                }
                service.files().create(
                    body=file_metadata, media_body=media, fields="id"
                ).execute()
            return path
        except Exception:
            logger.exception("put_file failed for %s", path)
            return None

    def get_file(self, path: str) -> bytes | None:
        try:
            service = self._get_service()
            if not service:
                return None

            parts = path.rsplit("/", 1)
            if len(parts) == 2:
                folder_path, filename = parts
            else:
                folder_path, filename = "", parts[0]

            root_id = self._find_or_create_folder(service, _ROOT_FOLDER)
            parent_id = root_id
            if folder_path:
                for segment in folder_path.split("/"):
                    parent_id = self._find_or_create_folder(
                        service, segment, parent_id=parent_id
                    )
                    if not parent_id:
                        return None

            file_id = self._find_file(service, parent_id, filename)
            if not file_id:
                return None

            return service.files().get_media(fileId=file_id).execute()
        except Exception:
            logger.exception("get_file failed for %s", path)
            return None

    def get_file_url(
        self,
        path: str,
        *,
        expires_in: int = 3600,
    ) -> str | None:
        try:
            service = self._get_service()
            if not service:
                return None

            parts = path.rsplit("/", 1)
            if len(parts) == 2:
                folder_path, filename = parts
            else:
                folder_path, filename = "", parts[0]

            root_id = self._find_or_create_folder(service, _ROOT_FOLDER)
            parent_id = root_id
            if folder_path:
                for segment in folder_path.split("/"):
                    parent_id = self._find_or_create_folder(
                        service, segment, parent_id=parent_id
                    )
                    if not parent_id:
                        return None

            file_id = self._find_file(service, parent_id, filename)
            if not file_id:
                return None

            return f"https://drive.google.com/uc?id={file_id}&export=download"
        except Exception:
            logger.exception("get_file_url failed for %s", path)
            return None

    def delete_file(self, path: str) -> bool:
        try:
            service = self._get_service()
            if not service:
                return False

            parts = path.rsplit("/", 1)
            if len(parts) == 2:
                folder_path, filename = parts
            else:
                folder_path, filename = "", parts[0]

            root_id = self._find_or_create_folder(service, _ROOT_FOLDER)
            parent_id = root_id
            if folder_path:
                for segment in folder_path.split("/"):
                    parent_id = self._find_or_create_folder(
                        service, segment, parent_id=parent_id
                    )
                    if not parent_id:
                        return False

            file_id = self._find_file(service, parent_id, filename)
            if not file_id:
                return False

            service.files().delete(fileId=file_id).execute()
            return True
        except Exception:
            logger.exception("delete_file failed for %s", path)
            return False

    def delete_all_files(self, prefix: str) -> int:
        try:
            service = self._get_service()
            if not service:
                return 0

            root_id = self._find_or_create_folder(service, _ROOT_FOLDER)
            parent_id = root_id
            if prefix:
                for segment in prefix.split("/"):
                    parent_id = self._find_or_create_folder(
                        service, segment, parent_id=parent_id
                    )
                    if not parent_id:
                        return 0

            query = f"'{parent_id}' in parents and trashed=false"
            results = (
                service.files()
                .list(q=query, spaces="drive", fields="files(id)")
                .execute()
            )
            files = results.get("files", [])
            for f in files:
                service.files().delete(fileId=f["id"]).execute()
            return len(files)
        except Exception:
            logger.exception("delete_all_files failed for prefix %s", prefix)
            return 0

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        try:
            service = self._get_service()
            if not service:
                return {
                    "ok": False,
                    "provider": "google_drive",
                    "error": "No valid token",
                }
            service.about().get(fields="user").execute()
            return {"ok": True, "provider": "google_drive"}
        except Exception as exc:
            logger.exception("health_check failed")
            return {"ok": False, "provider": "google_drive", "error": str(exc)}
