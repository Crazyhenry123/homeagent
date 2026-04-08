"""BaseRepository — abstract base for all entity repositories.

Encapsulates DynamoDB-specific logic so service code never touches boto3.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from app.dal.cursor import CursorCodec
from app.dal.exceptions import (
    ConditionalCheckError,
    DataAccessError,
    DuplicateEntityError,
    EntityNotFoundError,
    ThrottlingError,
)
from app.dal.pagination import PaginatedResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GSIConfig:
    """Describes a Global Secondary Index."""

    index_name: str
    partition_key: str
    sort_key: str | None = None


@dataclass(frozen=True)
class RepositoryConfig:
    """Configuration for a concrete repository."""

    table_name: str
    partition_key: str
    sort_key: str | None = None
    gsi_definitions: list[GSIConfig] = field(default_factory=list)
    has_version: bool = False


class BaseRepository:
    """Abstract base class for DynamoDB entity repositories.

    Provides typed CRUD, query, and batch operations with automatic
    timestamp management, optimistic locking, pagination, and
    exception translation.
    """

    BATCH_GET_LIMIT = 100
    BATCH_WRITE_LIMIT = 25
    UNPROCESSED_RETRIES = 3

    def __init__(
        self,
        config: RepositoryConfig,
        dynamodb_resource: Any,
        table_prefix: str = "",
    ) -> None:
        self._config = config
        self._dynamodb = dynamodb_resource
        self._table_prefix = table_prefix
        self._full_table_name = f"{table_prefix}{config.table_name}"
        self._table = dynamodb_resource.Table(self._full_table_name)

    @property
    def config(self) -> RepositoryConfig:
        return self._config

    @property
    def table_name(self) -> str:
        return self._full_table_name

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(self, item: dict[str, Any]) -> dict[str, Any]:
        """Create a new item with uniqueness check.

        Sets created_at and updated_at if not already present; always
        updates updated_at.  Sets version=1 when the repo uses versioning.
        Raises DuplicateEntityError if the item already exists.
        """
        now = datetime.now(timezone.utc).isoformat()
        item = {**item}  # shallow copy to avoid mutating caller's dict
        item.setdefault("created_at", now)
        item["updated_at"] = now
        if self._config.has_version:
            item.setdefault("version", 1)

        start = time.monotonic()
        try:
            self._table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(#pk)",
                ExpressionAttributeNames={"#pk": self._config.partition_key},
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise DuplicateEntityError(
                    f"Item already exists in {self._config.table_name}",
                    table_name=self._config.table_name,
                    operation="create",
                    key=self._extract_key(item),
                ) from exc
            self._translate_client_error(exc, "create", self._extract_key(item))
        finally:
            self._log_timing("create", start)

        return item

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get_by_id(self, key: dict[str, Any]) -> dict[str, Any] | None:
        """Get a single item by primary key. Returns None if not found."""
        start = time.monotonic()
        try:
            result = self._table.get_item(Key=key)
        except ClientError as exc:
            self._translate_client_error(exc, "get", key)
        finally:
            self._log_timing("get", start)
        return result.get("Item")

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
        """Query items by partition key with optional sort condition.

        Returns a PaginatedResult with opaque cursor for the next page.
        """
        pk_attr = self._config.partition_key
        if index_name:
            gsi = self._find_gsi(index_name)
            if gsi:
                pk_attr = gsi.partition_key

        key_expr = Key(pk_attr).eq(partition_value)
        if sort_condition is not None:
            key_expr = key_expr & sort_condition

        kwargs: dict[str, Any] = {
            "KeyConditionExpression": key_expr,
            "Limit": limit,
            "ScanIndexForward": scan_forward,
        }
        if index_name:
            kwargs["IndexName"] = index_name
        if filter_expression is not None:
            kwargs["FilterExpression"] = filter_expression

        exclusive_start_key = CursorCodec.decode(cursor)
        if exclusive_start_key is not None:
            kwargs["ExclusiveStartKey"] = exclusive_start_key

        start = time.monotonic()
        try:
            result = self._table.query(**kwargs)
        except ClientError as exc:
            self._translate_client_error(
                exc, "query", {"partition_value": partition_value}
            )
        finally:
            self._log_timing("query", start, index=index_name)

        items = result.get("Items", [])
        next_cursor = CursorCodec.encode(result.get("LastEvaluatedKey"))

        return PaginatedResult(items=items, next_cursor=next_cursor, count=len(items))

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        key: dict[str, Any],
        updates: dict[str, Any],
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        """Update an existing item. Returns the full updated item.

        When expected_version is provided, uses optimistic locking.
        Raises EntityNotFoundError if the item doesn't exist.
        Raises ConditionalCheckError on version mismatch.
        """
        if not updates:
            raise ValueError("updates must be non-empty")

        now = datetime.now(timezone.utc).isoformat()
        updates = {**updates, "updated_at": now}

        expr_parts: list[str] = []
        expr_names: dict[str, str] = {}
        expr_values: dict[str, Any] = {}

        for i, (field_name, value) in enumerate(updates.items()):
            name_ph = f"#k{i}"
            val_ph = f":v{i}"
            expr_parts.append(f"{name_ph} = {val_ph}")
            expr_names[name_ph] = field_name
            expr_values[val_ph] = value

        # Optimistic locking
        if expected_version is not None:
            expr_parts.append("#ver = :new_ver")
            expr_names["#ver"] = "version"
            expr_values[":new_ver"] = expected_version + 1
            expr_values[":expected_ver"] = expected_version

        expr_names["#pk_exists"] = self._config.partition_key
        condition = "attribute_exists(#pk_exists)"
        if expected_version is not None:
            condition += " AND #ver = :expected_ver"

        start = time.monotonic()
        try:
            result = self._table.update_item(
                Key=key,
                UpdateExpression="SET " + ", ".join(expr_parts),
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values,
                ConditionExpression=condition,
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                if expected_version is not None:
                    raise ConditionalCheckError(
                        f"Version conflict in {self._config.table_name}",
                        table_name=self._config.table_name,
                        operation="update",
                        key=key,
                        expected_version=expected_version,
                    ) from exc
                raise EntityNotFoundError(
                    f"Item not found in {self._config.table_name}",
                    table_name=self._config.table_name,
                    operation="update",
                    key=key,
                ) from exc
            self._translate_client_error(exc, "update", key)
        finally:
            self._log_timing("update", start)

        return result["Attributes"]

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    def upsert(self, item: dict[str, Any]) -> dict[str, Any]:
        """Insert or overwrite an item without uniqueness check.

        Unlike ``create()``, this does NOT use a condition expression,
        so it will overwrite any existing item with the same key.
        Automatically sets updated_at (and created_at if not present).
        """
        now = datetime.now(timezone.utc).isoformat()
        item.setdefault("created_at", now)
        item = {**item, "updated_at": now}

        start = time.monotonic()
        try:
            self._table.put_item(Item=item)
        except ClientError as exc:
            self._translate_client_error(exc, "upsert", self._extract_key(item))
        finally:
            self._log_timing("upsert", start)

        return item

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, key: dict[str, Any]) -> None:
        """Delete a single item by primary key."""
        start = time.monotonic()
        try:
            self._table.delete_item(Key=key)
        except ClientError as exc:
            self._translate_client_error(exc, "delete", key)
        finally:
            self._log_timing("delete", start)

    def delete_and_return(
        self,
        key: dict[str, Any],
        condition_expression: str | None = None,
        expression_attribute_names: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Atomically delete an item and return its old values.

        Returns the item that was deleted, or None if the condition
        failed (item didn't exist or condition wasn't met).
        """
        kwargs: dict[str, Any] = {"Key": key, "ReturnValues": "ALL_OLD"}
        if condition_expression:
            kwargs["ConditionExpression"] = condition_expression
        if expression_attribute_names:
            kwargs["ExpressionAttributeNames"] = expression_attribute_names

        start = time.monotonic()
        try:
            result = self._table.delete_item(**kwargs)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            self._translate_client_error(exc, "delete_and_return", key)
        finally:
            self._log_timing("delete_and_return", start)

        return result.get("Attributes")

    def conditional_delete(
        self,
        key: dict[str, Any],
        condition_expression: str,
        expression_attribute_names: dict[str, str] | None = None,
        expression_attribute_values: dict[str, Any] | None = None,
    ) -> bool:
        """Delete an item only if a condition is met. Returns True if deleted."""
        kwargs: dict[str, Any] = {
            "Key": key,
            "ConditionExpression": condition_expression,
        }
        if expression_attribute_names:
            kwargs["ExpressionAttributeNames"] = expression_attribute_names
        if expression_attribute_values:
            kwargs["ExpressionAttributeValues"] = expression_attribute_values

        start = time.monotonic()
        try:
            self._table.delete_item(**kwargs)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            self._translate_client_error(exc, "conditional_delete", key)
        finally:
            self._log_timing("conditional_delete", start)
        return False  # unreachable but satisfies type checker

    # ------------------------------------------------------------------
    # Batch Get
    # ------------------------------------------------------------------

    def batch_get(self, keys: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Batch get items by keys. Missing keys are silently omitted.

        Handles DynamoDB's 100-item limit via chunking and retries
        unprocessed keys with exponential backoff.
        """
        if not keys:
            return []

        all_items: list[dict[str, Any]] = []
        start = time.monotonic()

        for chunk_start in range(0, len(keys), self.BATCH_GET_LIMIT):
            chunk = keys[chunk_start : chunk_start + self.BATCH_GET_LIMIT]
            request_items = {self._full_table_name: {"Keys": chunk}}

            try:
                response = self._dynamodb.batch_get_item(RequestItems=request_items)
            except ClientError as exc:
                self._translate_client_error(exc, "batch_get", {})

            all_items.extend(
                response.get("Responses", {}).get(self._full_table_name, [])
            )

            # Retry unprocessed keys
            unprocessed = response.get("UnprocessedKeys", {})
            retries = 0
            while unprocessed and retries < self.UNPROCESSED_RETRIES:
                time.sleep(0.1 * (2**retries))
                try:
                    response = self._dynamodb.batch_get_item(RequestItems=unprocessed)
                except ClientError as exc:
                    self._translate_client_error(exc, "batch_get", {})
                all_items.extend(
                    response.get("Responses", {}).get(self._full_table_name, [])
                )
                unprocessed = response.get("UnprocessedKeys", {})
                retries += 1

        self._log_timing("batch_get", start, count=len(all_items))
        return all_items

    # ------------------------------------------------------------------
    # Batch Delete
    # ------------------------------------------------------------------

    def batch_delete(self, keys: list[dict[str, Any]]) -> None:
        """Batch delete items by keys using batch_writer."""
        if not keys:
            return

        start = time.monotonic()
        try:
            with self._table.batch_writer() as batch:
                for key in keys:
                    batch.delete_item(Key=key)
        except ClientError as exc:
            self._translate_client_error(exc, "batch_delete", {})
        finally:
            self._log_timing("batch_delete", start, count=len(keys))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _extract_key(self, item: dict[str, Any]) -> dict[str, Any]:
        """Extract the primary key fields from an item dict."""
        key = {self._config.partition_key: item[self._config.partition_key]}
        if self._config.sort_key and self._config.sort_key in item:
            key[self._config.sort_key] = item[self._config.sort_key]
        return key

    def _find_gsi(self, index_name: str) -> GSIConfig | None:
        """Find a GSI config by index name."""
        for gsi in self._config.gsi_definitions:
            if gsi.index_name == index_name:
                return gsi
        return None

    def _translate_client_error(
        self, exc: ClientError, operation: str, key: dict[str, Any]
    ) -> None:
        """Translate boto3 ClientError to the appropriate DAL exception."""
        code = exc.response["Error"]["Code"]
        msg = exc.response["Error"].get("Message", str(exc))

        if code in (
            "ProvisionedThroughputExceededException",
            "ThrottlingException",
            "RequestLimitExceeded",
        ):
            raise ThrottlingError(
                f"Throttled: {msg}",
                table_name=self._config.table_name,
                operation=operation,
                key=key,
            ) from exc

        raise DataAccessError(
            f"DynamoDB error in {self._config.table_name}.{operation}: {msg}",
            table_name=self._config.table_name,
            operation=operation,
            key=key,
        ) from exc

    def _log_timing(
        self,
        operation: str,
        start: float,
        index: str | None = None,
        count: int | None = None,
    ) -> None:
        """Emit structured timing log."""
        elapsed_ms = (time.monotonic() - start) * 1000
        extra: dict[str, Any] = {
            "table": self._config.table_name,
            "operation": operation,
            "duration_ms": round(elapsed_ms, 2),
        }
        if index:
            extra["index"] = index
        if count is not None:
            extra["count"] = count
        logger.debug(
            "DAL %s on %s (%.2fms)", operation, self._config.table_name, elapsed_ms
        )
