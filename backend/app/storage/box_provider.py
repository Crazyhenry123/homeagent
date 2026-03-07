"""Box storage provider implementation."""

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

_ROOT_FOLDER = "HomeAgent"

_KEY_FIELDS: dict[str, list[str]] = {
    COLLECTION_HEALTH_RECORDS: ["user_id", "record_id"],
    COLLECTION_HEALTH_OBSERVATIONS: ["user_id", "observation_id"],
    COLLECTION_HEALTH_DOCUMENTS: ["user_id", "document_id"],
    COLLECTION_HEALTH_AUDIT_LOG: ["record_id", "audit_sk"],
}


class BoxProvider(StorageProvider):
    """Store user data as JSON files in Box.

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

    def _get_client(self) -> Any | None:
        """Return an authenticated Box client."""
        try:
            from boxsdk import Client, OAuth2  # noqa: WPS433

            token = self._token_manager.get_valid_token("box")
            if not token:
                logger.error("No valid Box token for user=%s", self._user_id)
                return None

            oauth = OAuth2(
                client_id="",
                client_secret="",
                access_token=token,
            )
            return Client(oauth)
        except Exception:
            logger.exception("Failed to create Box client")
            return None

    def _find_or_create_folder(
        self, client: Any, name: str, parent_id: str = "0"
    ) -> str | None:
        """Find a subfolder by *name* under *parent_id*, or create it."""
        cache_key = f"{parent_id}:{name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        try:
            parent = client.folder(folder_id=parent_id)
            items = parent.get_items(limit=1000)
            for item in items:
                if item.type == "folder" and item.name == name:
                    self._folder_cache[cache_key] = item.id
                    return item.id

            # Create
            subfolder = parent.create_subfolder(name)
            self._folder_cache[cache_key] = subfolder.id
            return subfolder.id
        except Exception:
            logger.exception("Failed to find/create folder %s", name)
            return None

    def _get_collection_folder(self, client: Any, collection: str) -> str | None:
        """Return folder ID for HomeAgent/{collection}."""
        root_id = self._find_or_create_folder(client, _ROOT_FOLDER, "0")
        if not root_id:
            return None
        return self._find_or_create_folder(client, collection, root_id)

    def _find_file(
        self, client: Any, folder_id: str, filename: str
    ) -> str | None:
        """Find a file by name inside *folder_id*."""
        try:
            folder = client.folder(folder_id=folder_id)
            items = folder.get_items(limit=1000)
            for item in items:
                if item.type == "file" and item.name == filename:
                    return item.id
            return None
        except Exception:
            logger.exception("Failed to find file %s", filename)
            return None

    def _record_filename(self, key: dict[str, str]) -> str:
        parts = sorted(key.values())
        return "_".join(parts) + ".json"

    @staticmethod
    def _extract_key(collection: str, record: dict[str, Any]) -> dict[str, str]:
        """Extract only key fields from a record for filename derivation."""
        fields = _KEY_FIELDS.get(collection, [])
        if fields:
            return {f: str(record[f]) for f in fields if f in record}
        return {k: v for k, v in record.items() if isinstance(v, str)}

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
            import io  # noqa: WPS433

            client = self._get_client()
            if not client:
                return None

            folder_id = self._get_collection_folder(client, collection)
            if not folder_id:
                return None

            filename = self._record_filename(
                self._extract_key(collection, record)
            )
            data = json.dumps(record, default=str).encode("utf-8")
            stream = io.BytesIO(data)

            existing_id = self._find_file(client, folder_id, filename)
            if existing_id:
                client.file(file_id=existing_id).update_contents_with_stream(stream)
            else:
                folder = client.folder(folder_id=folder_id)
                folder.upload_stream(stream, filename)
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
            client = self._get_client()
            if not client:
                return None

            folder_id = self._get_collection_folder(client, collection)
            if not folder_id:
                return None

            filename = self._record_filename(key)
            file_id = self._find_file(client, folder_id, filename)
            if not file_id:
                return None

            content = client.file(file_id=file_id).content()
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
            client = self._get_client()
            if not client:
                return []

            folder_id = self._get_collection_folder(client, collection)
            if not folder_id:
                return []

            folder = client.folder(folder_id=folder_id)
            items = folder.get_items(limit=1000)

            records: list[dict[str, Any]] = []
            for item in items:
                if item.type != "file" or not item.name.endswith(".json"):
                    continue
                try:
                    content = client.file(file_id=item.id).content()
                    record = json.loads(content)
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
            client = self._get_client()
            if not client:
                return False

            folder_id = self._get_collection_folder(client, collection)
            if not folder_id:
                return False

            filename = self._record_filename(key)
            file_id = self._find_file(client, folder_id, filename)
            if not file_id:
                return False

            client.file(file_id=file_id).delete()
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
            client = self._get_client()
            if not client:
                return 0

            folder_id = self._get_collection_folder(client, collection)
            if not folder_id:
                return 0

            folder = client.folder(folder_id=folder_id)
            items = folder.get_items(limit=1000)

            pk_attr = list(partition_key.keys())[0]
            pk_value = partition_key[pk_attr]
            count = 0

            for item in items:
                if item.type != "file" or not item.name.endswith(".json"):
                    continue
                try:
                    content = client.file(file_id=item.id).content()
                    record = json.loads(content)
                    if record.get(pk_attr) == pk_value:
                        client.file(file_id=item.id).delete()
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
            import io  # noqa: WPS433

            client = self._get_client()
            if not client:
                return None

            parts = path.rsplit("/", 1)
            if len(parts) == 2:
                folder_path, filename = parts
            else:
                folder_path, filename = "", parts[0]

            # Navigate/create folder hierarchy under HomeAgent
            root_id = self._find_or_create_folder(client, _ROOT_FOLDER, "0")
            parent_id = root_id
            if folder_path:
                for segment in folder_path.split("/"):
                    parent_id = self._find_or_create_folder(
                        client, segment, parent_id
                    )
                    if not parent_id:
                        return None

            stream = io.BytesIO(data)
            existing_id = self._find_file(client, parent_id, filename)
            if existing_id:
                client.file(file_id=existing_id).update_contents_with_stream(stream)
            else:
                folder = client.folder(folder_id=parent_id)
                folder.upload_stream(stream, filename)
            return path
        except Exception:
            logger.exception("put_file failed for %s", path)
            return None

    def get_file(self, path: str) -> bytes | None:
        try:
            client = self._get_client()
            if not client:
                return None

            parts = path.rsplit("/", 1)
            if len(parts) == 2:
                folder_path, filename = parts
            else:
                folder_path, filename = "", parts[0]

            root_id = self._find_or_create_folder(client, _ROOT_FOLDER, "0")
            parent_id = root_id
            if folder_path:
                for segment in folder_path.split("/"):
                    parent_id = self._find_or_create_folder(
                        client, segment, parent_id
                    )
                    if not parent_id:
                        return None

            file_id = self._find_file(client, parent_id, filename)
            if not file_id:
                return None

            return client.file(file_id=file_id).content()
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
            client = self._get_client()
            if not client:
                return None

            parts = path.rsplit("/", 1)
            if len(parts) == 2:
                folder_path, filename = parts
            else:
                folder_path, filename = "", parts[0]

            root_id = self._find_or_create_folder(client, _ROOT_FOLDER, "0")
            parent_id = root_id
            if folder_path:
                for segment in folder_path.split("/"):
                    parent_id = self._find_or_create_folder(
                        client, segment, parent_id
                    )
                    if not parent_id:
                        return None

            file_id = self._find_file(client, parent_id, filename)
            if not file_id:
                return None

            return client.file(file_id=file_id).get_shared_link_download_url(
                access="open"
            )
        except Exception:
            logger.exception("get_file_url failed for %s", path)
            return None

    def delete_file(self, path: str) -> bool:
        try:
            client = self._get_client()
            if not client:
                return False

            parts = path.rsplit("/", 1)
            if len(parts) == 2:
                folder_path, filename = parts
            else:
                folder_path, filename = "", parts[0]

            root_id = self._find_or_create_folder(client, _ROOT_FOLDER, "0")
            parent_id = root_id
            if folder_path:
                for segment in folder_path.split("/"):
                    parent_id = self._find_or_create_folder(
                        client, segment, parent_id
                    )
                    if not parent_id:
                        return False

            file_id = self._find_file(client, parent_id, filename)
            if not file_id:
                return False

            client.file(file_id=file_id).delete()
            return True
        except Exception:
            logger.exception("delete_file failed for %s", path)
            return False

    def delete_all_files(self, prefix: str) -> int:
        try:
            client = self._get_client()
            if not client:
                return 0

            root_id = self._find_or_create_folder(client, _ROOT_FOLDER, "0")
            parent_id = root_id
            if prefix:
                for segment in prefix.split("/"):
                    parent_id = self._find_or_create_folder(
                        client, segment, parent_id
                    )
                    if not parent_id:
                        return 0

            folder = client.folder(folder_id=parent_id)
            items = folder.get_items(limit=1000)
            count = 0
            for item in items:
                if item.type == "file":
                    try:
                        client.file(file_id=item.id).delete()
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
            client = self._get_client()
            if not client:
                return {
                    "ok": False,
                    "provider": "box",
                    "error": "No valid token",
                }
            client.user().get()
            return {"ok": True, "provider": "box"}
        except Exception as exc:
            logger.exception("health_check failed")
            return {"ok": False, "provider": "box", "error": str(exc)}
