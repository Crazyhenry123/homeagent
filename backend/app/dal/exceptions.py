"""Database-agnostic exception hierarchy for the DAL.

Service code catches these instead of boto3-specific exceptions.
"""

from __future__ import annotations

from typing import Any


class DataAccessError(Exception):
    """Base class for all DAL errors."""

    def __init__(
        self,
        message: str,
        table_name: str = "",
        operation: str = "",
        key: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.table_name = table_name
        self.operation = operation
        self.key = key or {}


class EntityNotFoundError(DataAccessError):
    """Item not found by key lookup."""


class DuplicateEntityError(DataAccessError):
    """Conditional put failed because the item already exists."""


class ConditionalCheckError(DataAccessError):
    """Generic conditional check failure (e.g. version mismatch)."""

    def __init__(
        self,
        message: str,
        table_name: str = "",
        operation: str = "",
        key: dict[str, Any] | None = None,
        expected_version: int | None = None,
    ) -> None:
        super().__init__(message, table_name, operation, key)
        self.expected_version = expected_version


class TransactionConflictError(DataAccessError):
    """TransactWriteItems conflict or cancellation."""

    def __init__(
        self,
        message: str,
        table_name: str = "",
        operation: str = "transact_write",
        key: dict[str, Any] | None = None,
        cancellation_reasons: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message, table_name, operation, key)
        self.cancellation_reasons = cancellation_reasons or []


class ThrottlingError(DataAccessError):
    """Raised after retries for throttled operations are exhausted."""
