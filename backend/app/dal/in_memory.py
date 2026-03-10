"""In-memory repository for unit testing.

Implements the same interface as BaseRepository but stores data in
Python dicts. No DynamoDB dependency required.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from app.dal.cursor import CursorCodec
from app.dal.exceptions import (
    ConditionalCheckError,
    DuplicateEntityError,
    EntityNotFoundError,
)
from app.dal.pagination import PaginatedResult


class InMemoryRepository:
    """Dict-backed repository with the same interface as BaseRepository.

    Suitable for unit tests that don't need real DynamoDB.
    """

    def __init__(
        self,
        partition_key: str,
        sort_key: str | None = None,
        has_version: bool = False,
    ) -> None:
        self._partition_key = partition_key
        self._sort_key = sort_key
        self._has_version = has_version
        self._store: dict[str, dict[str, Any]] = {}

    def _make_key_str(self, key: dict[str, Any]) -> str:
        """Build a string key from PK (and SK if present)."""
        pk = str(key[self._partition_key])
        if self._sort_key and self._sort_key in key:
            return f"{pk}##{key[self._sort_key]}"
        return pk

    def _extract_key(self, item: dict[str, Any]) -> dict[str, Any]:
        key = {self._partition_key: item[self._partition_key]}
        if self._sort_key and self._sort_key in item:
            key[self._sort_key] = item[self._sort_key]
        return key

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, item: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        item = {**item, "created_at": now, "updated_at": now}
        if self._has_version:
            item["version"] = 1

        key_str = self._make_key_str(item)
        if key_str in self._store:
            raise DuplicateEntityError(
                "Item already exists",
                operation="create",
                key=self._extract_key(item),
            )
        self._store[key_str] = copy.deepcopy(item)
        return copy.deepcopy(item)

    def get_by_id(self, key: dict[str, Any]) -> dict[str, Any] | None:
        key_str = self._make_key_str(key)
        item = self._store.get(key_str)
        return copy.deepcopy(item) if item else None

    def update(
        self,
        key: dict[str, Any],
        updates: dict[str, Any],
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        if not updates:
            raise ValueError("updates must be non-empty")

        key_str = self._make_key_str(key)
        item = self._store.get(key_str)
        if item is None:
            if expected_version is not None:
                raise ConditionalCheckError(
                    "Version conflict: item not found",
                    operation="update",
                    key=key,
                    expected_version=expected_version,
                )
            raise EntityNotFoundError(
                "Item not found",
                operation="update",
                key=key,
            )

        if expected_version is not None and item.get("version") != expected_version:
            raise ConditionalCheckError(
                f"Version conflict: expected {expected_version}, got {item.get('version')}",
                operation="update",
                key=key,
                expected_version=expected_version,
            )

        now = datetime.now(timezone.utc).isoformat()
        item.update(updates)
        item["updated_at"] = now
        if expected_version is not None:
            item["version"] = expected_version + 1

        return copy.deepcopy(item)

    def delete(self, key: dict[str, Any]) -> None:
        key_str = self._make_key_str(key)
        self._store.pop(key_str, None)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        partition_value: str,
        sort_condition: Any | None = None,
        index_name: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
        scan_forward: bool = True,
        filter_expression: Any | None = None,
    ) -> PaginatedResult[dict[str, Any]]:
        """Query by partition key with offset-based pagination.

        Note: index_name, sort_condition, and filter_expression are
        simplified — GSI queries do a linear scan over all items.
        """
        # Find matching items
        matching = []
        for item in self._store.values():
            if str(item.get(self._partition_key)) == partition_value:
                matching.append(copy.deepcopy(item))

        # Sort by sort key if present
        if self._sort_key:
            matching.sort(
                key=lambda x: str(x.get(self._sort_key, "")),
                reverse=not scan_forward,
            )

        # Decode cursor as offset
        offset = 0
        if cursor is not None:
            decoded = CursorCodec.decode(cursor)
            if decoded and "__offset" in decoded:
                offset = decoded["__offset"]

        page = matching[offset : offset + limit]
        next_offset = offset + limit
        next_cursor = None
        if next_offset < len(matching):
            next_cursor = CursorCodec.encode({"__offset": next_offset})

        return PaginatedResult(items=page, next_cursor=next_cursor, count=len(page))

    # ------------------------------------------------------------------
    # Batch operations
    # ------------------------------------------------------------------

    def batch_get(self, keys: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results = []
        for key in keys:
            item = self.get_by_id(key)
            if item is not None:
                results.append(item)
        return results

    def batch_delete(self, keys: list[dict[str, Any]]) -> None:
        for key in keys:
            self.delete(key)
