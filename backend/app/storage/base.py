"""Abstract base class for storage providers."""

from __future__ import annotations

import abc
from typing import Any

# Collection name constants
COLLECTION_HEALTH_RECORDS = "health_records"
COLLECTION_HEALTH_OBSERVATIONS = "health_observations"
COLLECTION_HEALTH_DOCUMENTS = "health_documents_meta"
COLLECTION_HEALTH_AUDIT_LOG = "health_audit_log"


class StorageProvider(abc.ABC):
    """Abstract interface for user data storage.

    Implementations may store structured records (DynamoDB, JSON files)
    and binary files (S3, cloud drive files) using provider-specific backends.
    """

    # -- Structured record operations --

    @abc.abstractmethod
    def put_record(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        condition_expression: str | None = None,
    ) -> dict[str, Any] | None:
        """Insert or replace a record in *collection*.

        Returns the stored record on success, or ``None`` on failure.
        """
        ...

    @abc.abstractmethod
    def get_record(
        self,
        collection: str,
        key: dict[str, str],
    ) -> dict[str, Any] | None:
        """Fetch a single record by its primary key.

        Returns the record dict, or ``None`` if not found.
        """
        ...

    @abc.abstractmethod
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
        """Query records matching *key_condition*.

        Parameters
        ----------
        collection:
            Logical collection name.
        key_condition:
            Mapping of attribute names to match values.  For the sort key the
            value may be a ``(operator, value)`` tuple, e.g. ``("begins_with", "prefix")``.
        index_name:
            Optional secondary index to query.
        filter_expression:
            Additional post-query filter criteria.
        limit:
            Maximum number of records to return.
        scan_forward:
            ``True`` for ascending sort-key order (default).

        Returns a (possibly empty) list of record dicts.
        """
        ...

    @abc.abstractmethod
    def update_record(
        self,
        collection: str,
        key: dict[str, str],
        updates: dict[str, Any],
        *,
        condition_expression: str | None = None,
    ) -> dict[str, Any] | None:
        """Partially update a record identified by *key*.

        Returns the updated record, or ``None`` on failure.
        """
        ...

    @abc.abstractmethod
    def delete_record(
        self,
        collection: str,
        key: dict[str, str],
    ) -> bool:
        """Delete a single record.  Returns ``True`` on success."""
        ...

    @abc.abstractmethod
    def delete_all_records(
        self,
        collection: str,
        partition_key: dict[str, str],
    ) -> int:
        """Delete all records sharing the given partition key.

        Returns the number of records deleted.
        """
        ...

    # -- File / binary object operations --

    @abc.abstractmethod
    def put_file(
        self,
        path: str,
        data: bytes,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str | None:
        """Store a binary file at *path*.

        Returns the storage key/path on success, or ``None`` on failure.
        """
        ...

    @abc.abstractmethod
    def get_file(self, path: str) -> bytes | None:
        """Retrieve the raw bytes of a file.  Returns ``None`` if missing."""
        ...

    @abc.abstractmethod
    def get_file_url(
        self,
        path: str,
        *,
        expires_in: int = 3600,
    ) -> str | None:
        """Generate a time-limited URL to access the file.

        Returns ``None`` if the file does not exist or URLs are unsupported.
        """
        ...

    @abc.abstractmethod
    def delete_file(self, path: str) -> bool:
        """Delete a file.  Returns ``True`` on success."""
        ...

    @abc.abstractmethod
    def delete_all_files(self, prefix: str) -> int:
        """Delete all files under *prefix*.  Returns count deleted."""
        ...

    # -- Health check --

    @abc.abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Return a dict with at least ``{"ok": bool}`` describing provider health."""
        ...
