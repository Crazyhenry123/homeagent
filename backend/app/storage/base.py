"""Abstract base class for storage providers."""
from __future__ import annotations

from abc import ABC, abstractmethod


class StorageProvider(ABC):
    @abstractmethod
    def put_record(
        self, user_id: str, collection: str, record_id: str, data: dict
    ) -> dict: ...

    @abstractmethod
    def get_record(
        self, user_id: str, collection: str, record_id: str
    ) -> dict | None: ...

    @abstractmethod
    def query_records(
        self,
        user_id: str,
        collection: str,
        index_name: str | None = None,
        filter_key: str | None = None,
        filter_value: str | None = None,
    ) -> list[dict]: ...

    @abstractmethod
    def delete_record(
        self, user_id: str, collection: str, record_id: str
    ) -> bool: ...

    @abstractmethod
    def delete_all_records(self, user_id: str, collection: str) -> None: ...

    @abstractmethod
    def put_file(
        self, user_id: str, path: str, data: bytes, content_type: str
    ) -> str: ...

    @abstractmethod
    def get_file(self, user_id: str, path: str) -> tuple[bytes, str] | None: ...

    @abstractmethod
    def get_file_url(
        self, user_id: str, path: str, expiry: int = 3600
    ) -> str | None: ...

    @abstractmethod
    def delete_file(self, user_id: str, path: str) -> bool: ...

    @abstractmethod
    def delete_all_files(self, user_id: str, prefix: str) -> None: ...


COLLECTION_HEALTH_RECORDS = "health_records"
COLLECTION_HEALTH_OBSERVATIONS = "health_observations"
COLLECTION_HEALTH_DOCUMENTS = "health_documents_meta"
