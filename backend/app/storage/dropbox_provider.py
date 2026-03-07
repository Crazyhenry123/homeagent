"""Dropbox storage provider implementation."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.storage.base import (
    COLLECTION_HEALTH_AUDIT_LOG,
    COLLECTION_HEALTH_DOCUMENTS,
    COLLECTION_HEALTH_OBSERVATIONS,
    COLLECTION_HEALTH_RECORDS,
    StorageProvider,
)
from app.storage.token_manager import OAuthTokenManager

logger = logging.getLogger(__name__)

_ROOT_PATH = "/Apps/HomeAgent"

_KEY_FIELDS: dict[str, list[str]] = {
    COLLECTION_HEALTH_RECORDS: ["user_id", "record_id"],
    COLLECTION_HEALTH_OBSERVATIONS: ["user_id", "observation_id"],
    COLLECTION_HEALTH_DOCUMENTS: ["user_id", "document_id"],
    COLLECTION_HEALTH_AUDIT_LOG: ["record_id", "audit_sk"],
}


class DropboxProvider(StorageProvider):
    """Store user data as JSON files in Dropbox.

    Path layout::

        /Apps/HomeAgent/{collection}/{record_id}.json
    """

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id
        self._token_manager = OAuthTokenManager(user_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> Any | None:
        """Return an authenticated Dropbox client."""
        try:
            import dropbox  # noqa: WPS433

            token = self._token_manager.get_valid_token("dropbox")
            if not token:
                logger.error(
                    "No valid Dropbox token for user=%s", self._user_id
                )
                return None
            return dropbox.Dropbox(token)
        except Exception:
            logger.exception("Failed to create Dropbox client")
            return None

    def _collection_path(self, collection: str) -> str:
        return f"{_ROOT_PATH}/{collection}"

    def _record_path(self, collection: str, key: dict[str, str]) -> str:
        parts = sorted(key.values())
        filename = "_".join(parts) + ".json"
        return f"{_ROOT_PATH}/{collection}/{filename}"

    @staticmethod
    def _extract_key(collection: str, record: dict[str, Any]) -> dict[str, str]:
        """Extract only key fields from a record for filename derivation."""
        fields = _KEY_FIELDS.get(collection, [])
        if fields:
            return {f: str(record[f]) for f in fields if f in record}
        return {k: v for k, v in record.items() if isinstance(v, str)}

    def _ensure_folder(self, dbx: Any, path: str) -> None:
        """Create folder if it doesn't exist."""
        try:
            dbx.files_get_metadata(path)
        except Exception:
            try:
                dbx.files_create_folder_v2(path)
            except Exception:
                pass  # Folder may already exist via race condition

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
            import dropbox as dbx_module  # noqa: WPS433

            dbx = self._get_client()
            if not dbx:
                return None

            self._ensure_folder(dbx, self._collection_path(collection))

            path = self._record_path(
                collection,
                self._extract_key(collection, record),
            )
            data = json.dumps(record, default=str).encode("utf-8")
            dbx.files_upload(
                data,
                path,
                mode=dbx_module.files.WriteMode.overwrite,
            )
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
            dbx = self._get_client()
            if not dbx:
                return None

            path = self._record_path(collection, key)
            _, response = dbx.files_download(path)
            return json.loads(response.content)
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
            dbx = self._get_client()
            if not dbx:
                return []

            folder_path = self._collection_path(collection)
            try:
                result = dbx.files_list_folder(folder_path)
            except Exception:
                return []

            entries = result.entries
            while result.has_more:
                result = dbx.files_list_folder_continue(result.cursor)
                entries.extend(result.entries)

            records: list[dict[str, Any]] = []
            for entry in entries:
                if not entry.name.endswith(".json"):
                    continue
                try:
                    _, response = dbx.files_download(entry.path_lower)
                    record = json.loads(response.content)
                except Exception:
                    continue

                match = True
                for attr, value in key_condition.items():
                    if isinstance(value, tuple):
                        op, val = value
                        rec_val = record.get(attr, "")
                        if op == "begins_with":
                            if not str(rec_val).startswith(str(val)):
                                match = False
                        elif op == "between":
                            if not (str(val[0]) <= str(rec_val) <= str(val[1])):
                                match = False
                        elif op == "gte":
                            if str(rec_val) < str(val):
                                match = False
                        elif op == "lte":
                            if str(rec_val) > str(val):
                                match = False
                        elif op == "eq":
                            if rec_val != val:
                                match = False
                        else:
                            if rec_val != val:
                                match = False
                    else:
                        if record.get(attr) != value:
                            match = False

                if filter_expression and match:
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
            dbx = self._get_client()
            if not dbx:
                return False
            path = self._record_path(collection, key)
            dbx.files_delete_v2(path)
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
            dbx = self._get_client()
            if not dbx:
                return 0

            folder_path = self._collection_path(collection)
            try:
                result = dbx.files_list_folder(folder_path)
            except Exception:
                return 0

            entries = result.entries
            while result.has_more:
                result = dbx.files_list_folder_continue(result.cursor)
                entries.extend(result.entries)

            pk_attr = list(partition_key.keys())[0]
            pk_value = partition_key[pk_attr]
            count = 0

            for entry in entries:
                if not entry.name.endswith(".json"):
                    continue
                try:
                    _, response = dbx.files_download(entry.path_lower)
                    record = json.loads(response.content)
                    if record.get(pk_attr) == pk_value:
                        dbx.files_delete_v2(entry.path_lower)
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
            import dropbox as dbx_module  # noqa: WPS433

            dbx = self._get_client()
            if not dbx:
                return None

            full_path = f"{_ROOT_PATH}/{path}"
            # Ensure parent folder
            parent = full_path.rsplit("/", 1)[0]
            self._ensure_folder(dbx, parent)

            dbx.files_upload(
                data,
                full_path,
                mode=dbx_module.files.WriteMode.overwrite,
            )
            return path
        except Exception:
            logger.exception("put_file failed for %s", path)
            return None

    def get_file(self, path: str) -> bytes | None:
        try:
            dbx = self._get_client()
            if not dbx:
                return None
            full_path = f"{_ROOT_PATH}/{path}"
            _, response = dbx.files_download(full_path)
            return response.content
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
            dbx = self._get_client()
            if not dbx:
                return None
            full_path = f"{_ROOT_PATH}/{path}"
            link = dbx.files_get_temporary_link(full_path)
            return link.link
        except Exception:
            logger.exception("get_file_url failed for %s", path)
            return None

    def delete_file(self, path: str) -> bool:
        try:
            dbx = self._get_client()
            if not dbx:
                return False
            full_path = f"{_ROOT_PATH}/{path}"
            dbx.files_delete_v2(full_path)
            return True
        except Exception:
            logger.exception("delete_file failed for %s", path)
            return False

    def delete_all_files(self, prefix: str) -> int:
        try:
            dbx = self._get_client()
            if not dbx:
                return 0

            full_path = f"{_ROOT_PATH}/{prefix}"
            try:
                result = dbx.files_list_folder(full_path)
            except Exception:
                return 0

            entries = result.entries
            while result.has_more:
                result = dbx.files_list_folder_continue(result.cursor)
                entries.extend(result.entries)

            count = 0
            for entry in entries:
                try:
                    dbx.files_delete_v2(entry.path_lower)
                    count += 1
                except Exception:
                    continue
            return count
        except Exception:
            logger.exception("delete_all_files failed for prefix %s", prefix)
            return 0

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        try:
            dbx = self._get_client()
            if not dbx:
                return {
                    "ok": False,
                    "provider": "dropbox",
                    "error": "No valid token",
                }
            dbx.users_get_current_account()
            return {"ok": True, "provider": "dropbox"}
        except Exception as exc:
            logger.exception("health_check failed")
            return {"ok": False, "provider": "dropbox", "error": str(exc)}
