"""Microsoft OneDrive storage provider using the Graph API."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from app.storage.base import (
    COLLECTION_HEALTH_DOCUMENTS,
    COLLECTION_HEALTH_OBSERVATIONS,
    COLLECTION_HEALTH_RECORDS,
    StorageProvider,
)
from app.storage.token_manager import OAuthTokenManager

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_ROOT_PATH = "HomeAgent"

_KEY_FIELDS: dict[str, list[str]] = {
    COLLECTION_HEALTH_RECORDS: ["user_id", "record_id"],
    COLLECTION_HEALTH_OBSERVATIONS: ["user_id", "observation_id"],
    COLLECTION_HEALTH_DOCUMENTS: ["user_id", "document_id"],
}


class OneDriveProvider(StorageProvider):
    """Store user data as JSON files in OneDrive.

    Path layout::

        /me/drive/root:/HomeAgent/{collection}/{record_id}.json
    """

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id
        self._token_manager = OAuthTokenManager(user_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str] | None:
        token = self._token_manager.get_valid_token("onedrive")
        if not token:
            logger.error("No valid OneDrive token for user=%s", self._user_id)
            return None
        return {"Authorization": f"Bearer {token}"}

    def _item_path(self, *segments: str) -> str:
        """Build a Graph API item-by-path URL."""
        path = "/".join(segments)
        return f"{_GRAPH_BASE}/me/drive/root:/{_ROOT_PATH}/{path}"

    @staticmethod
    def _record_filename(key: dict[str, str]) -> str:
        parts = sorted(key.values())
        return "_".join(parts) + ".json"

    @staticmethod
    def _extract_key(collection: str, record: dict[str, Any]) -> dict[str, str]:
        """Extract only key fields from a record for filename derivation."""
        fields = _KEY_FIELDS.get(collection, [])
        if fields:
            return {f: str(record[f]) for f in fields if f in record}
        return {k: v for k, v in record.items() if isinstance(v, str)}

    def _ensure_folder(self, path: str) -> bool:
        """Create a folder if it doesn't exist (PUT with folder facet)."""
        headers = self._headers()
        if not headers:
            return False
        url = f"{_GRAPH_BASE}/me/drive/root:/{_ROOT_PATH}/{path}"
        # Check existence
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return True
        # Create via parent children endpoint
        parts = path.rsplit("/", 1)
        if len(parts) == 2:
            parent_path, folder_name = parts
            parent_url = (
                f"{_GRAPH_BASE}/me/drive/root:/{_ROOT_PATH}/{parent_path}:/children"
            )
        else:
            folder_name = parts[0]
            parent_url = f"{_GRAPH_BASE}/me/drive/root:/{_ROOT_PATH}:/children"
        body = {
            "name": folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail",
        }
        resp = requests.post(
            parent_url, headers={**headers, "Content-Type": "application/json"},
            json=body, timeout=30,
        )
        return resp.status_code in (200, 201, 409)  # 409 = already exists

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
            headers = self._headers()
            if not headers:
                return None
            self._ensure_folder(collection)

            filename = self._record_filename(
                self._extract_key(collection, record)
            )
            url = self._item_path(collection, filename) + ":/content"
            data = json.dumps(record, default=str).encode("utf-8")
            resp = requests.put(
                url,
                headers={**headers, "Content-Type": "application/json"},
                data=data,
                timeout=30,
            )
            if resp.status_code in (200, 201):
                return record
            logger.error("put_record returned %s: %s", resp.status_code, resp.text)
            return None
        except Exception:
            logger.exception("put_record failed for %s", collection)
            return None

    def get_record(
        self,
        collection: str,
        key: dict[str, str],
    ) -> dict[str, Any] | None:
        try:
            headers = self._headers()
            if not headers:
                return None
            filename = self._record_filename(key)
            url = self._item_path(collection, filename) + ":/content"
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            return None
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
            headers = self._headers()
            if not headers:
                return []

            url = self._item_path(collection) + ":/children"
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                return []

            items = resp.json().get("value", [])
            records: list[dict[str, Any]] = []

            for item in items:
                if not item.get("name", "").endswith(".json"):
                    continue
                download_url = item.get("@microsoft.graph.downloadUrl")
                if not download_url:
                    continue
                content_resp = requests.get(download_url, timeout=30)
                if content_resp.status_code != 200:
                    continue
                record = content_resp.json()

                # Filter by key_condition
                match = True
                for attr, value in key_condition.items():
                    if isinstance(value, tuple):
                        op, val = value
                        rec_val = record.get(attr, "")
                        if op == "begins_with" and not str(rec_val).startswith(str(val)):
                            match = False
                        elif op == "eq" and rec_val != val:
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
            headers = self._headers()
            if not headers:
                return False
            filename = self._record_filename(key)
            url = self._item_path(collection, filename)
            resp = requests.delete(url, headers=headers, timeout=30)
            return resp.status_code in (200, 204)
        except Exception:
            logger.exception("delete_record failed for %s", collection)
            return False

    def delete_all_records(
        self,
        collection: str,
        partition_key: dict[str, str],
    ) -> int:
        try:
            headers = self._headers()
            if not headers:
                return 0

            url = self._item_path(collection) + ":/children"
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                return 0

            items = resp.json().get("value", [])
            pk_attr = list(partition_key.keys())[0]
            pk_value = partition_key[pk_attr]
            count = 0

            for item in items:
                if not item.get("name", "").endswith(".json"):
                    continue
                download_url = item.get("@microsoft.graph.downloadUrl")
                if not download_url:
                    continue
                content_resp = requests.get(download_url, timeout=30)
                if content_resp.status_code != 200:
                    continue
                record = content_resp.json()
                if record.get(pk_attr) == pk_value:
                    item_id = item["id"]
                    del_url = f"{_GRAPH_BASE}/me/drive/items/{item_id}"
                    del_resp = requests.delete(del_url, headers=headers, timeout=30)
                    if del_resp.status_code in (200, 204):
                        count += 1
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
            headers = self._headers()
            if not headers:
                return None

            # Ensure parent folders exist
            parts = path.rsplit("/", 1)
            if len(parts) == 2:
                self._ensure_folder(parts[0])

            url = self._item_path(path) + ":/content"
            resp = requests.put(
                url,
                headers={
                    **headers,
                    "Content-Type": content_type or "application/octet-stream",
                },
                data=data,
                timeout=60,
            )
            if resp.status_code in (200, 201):
                return path
            logger.error("put_file returned %s: %s", resp.status_code, resp.text)
            return None
        except Exception:
            logger.exception("put_file failed for %s", path)
            return None

    def get_file(self, path: str) -> bytes | None:
        try:
            headers = self._headers()
            if not headers:
                return None
            url = self._item_path(path) + ":/content"
            resp = requests.get(url, headers=headers, timeout=60)
            if resp.status_code == 200:
                return resp.content
            return None
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
            headers = self._headers()
            if not headers:
                return None
            url = self._item_path(path)
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                return None
            item_id = resp.json().get("id")
            if not item_id:
                return None
            # Create sharing link
            link_url = f"{_GRAPH_BASE}/me/drive/items/{item_id}/createLink"
            link_resp = requests.post(
                link_url,
                headers={**headers, "Content-Type": "application/json"},
                json={"type": "view", "scope": "anonymous"},
                timeout=30,
            )
            if link_resp.status_code in (200, 201):
                return link_resp.json().get("link", {}).get("webUrl")
            return None
        except Exception:
            logger.exception("get_file_url failed for %s", path)
            return None

    def delete_file(self, path: str) -> bool:
        try:
            headers = self._headers()
            if not headers:
                return False
            url = self._item_path(path)
            resp = requests.delete(url, headers=headers, timeout=30)
            return resp.status_code in (200, 204)
        except Exception:
            logger.exception("delete_file failed for %s", path)
            return False

    def delete_all_files(self, prefix: str) -> int:
        try:
            headers = self._headers()
            if not headers:
                return 0
            url = self._item_path(prefix) + ":/children"
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                return 0
            items = resp.json().get("value", [])
            count = 0
            for item in items:
                item_id = item["id"]
                del_url = f"{_GRAPH_BASE}/me/drive/items/{item_id}"
                del_resp = requests.delete(del_url, headers=headers, timeout=30)
                if del_resp.status_code in (200, 204):
                    count += 1
            return count
        except Exception:
            logger.exception("delete_all_files failed for prefix %s", prefix)
            return 0

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        try:
            headers = self._headers()
            if not headers:
                return {
                    "ok": False,
                    "provider": "onedrive",
                    "error": "No valid token",
                }
            resp = requests.get(
                f"{_GRAPH_BASE}/me/drive", headers=headers, timeout=30
            )
            if resp.status_code == 200:
                return {"ok": True, "provider": "onedrive"}
            return {
                "ok": False,
                "provider": "onedrive",
                "error": f"HTTP {resp.status_code}",
            }
        except Exception as exc:
            logger.exception("health_check failed")
            return {"ok": False, "provider": "onedrive", "error": str(exc)}
