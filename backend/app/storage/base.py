"""Abstract base class for storage providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class StorageProvider(ABC):
    @abstractmethod
    def put_record(
        self,
        collection: str,
        record: dict[str, Any],
        *,
        condition_expression: str | None = None,
    ) -> dict[str, Any] | None: ...

    @abstractmethod
    def get_record(
        self,
        collection: str,
        key: dict[str, str],
    ) -> dict[str, Any] | None: ...

    @abstractmethod
    def query_records(
        self,
        collection: str,
        key_condition: dict[str, Any],
        *,
        index_name: str | None = None,
        filter_expression: dict[str, Any] | None = None,
        limit: int | None = None,
        scan_forward: bool = True,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    def update_record(
        self,
        collection: str,
        key: dict[str, str],
        updates: dict[str, Any],
        *,
        condition_expression: str | None = None,
    ) -> dict[str, Any] | None: ...

    @abstractmethod
    def delete_record(
        self,
        collection: str,
        key: dict[str, str],
    ) -> bool: ...

    @abstractmethod
    def delete_all_records(
        self,
        collection: str,
        partition_key: dict[str, str],
    ) -> int: ...

    @abstractmethod
    def put_file(
        self,
        path: str,
        data: bytes,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str | None: ...

    @abstractmethod
    def get_file(self, path: str) -> bytes | None: ...

    @abstractmethod
    def get_file_url(
        self,
        path: str,
        *,
        expires_in: int = 3600,
    ) -> str | None: ...

    @abstractmethod
    def delete_file(self, path: str) -> bool: ...

    @abstractmethod
    def delete_all_files(self, prefix: str) -> int: ...

    @abstractmethod
    def health_check(self) -> dict[str, Any]: ...


COLLECTION_HEALTH_RECORDS = "health_records"
COLLECTION_HEALTH_OBSERVATIONS = "health_observations"
COLLECTION_HEALTH_DOCUMENTS = "health_documents_meta"
COLLECTION_HEALTH_AUDIT_LOG = "health_audit_log"
