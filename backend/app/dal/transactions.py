"""TransactionHelper — atomic multi-table DynamoDB operations.

Wraps TransactWriteItems to provide atomic put/update/delete/condition_check
across multiple tables.
"""

from __future__ import annotations

import decimal
import logging
import time
from typing import Any

from botocore.exceptions import ClientError

from app.dal.exceptions import DataAccessError, TransactionConflictError

logger = logging.getLogger(__name__)

# DynamoDB TransactWriteItems limit
MAX_TRANSACTION_ITEMS = 100


class TransactionHelper:
    """Collects write operations and commits them atomically.

    Usage::

        with TransactionHelper(dynamodb_client) as tx:
            tx.add_put("Users", user_item)
            tx.add_put("Memberships", membership_item)
            tx.add_update("Families", family_key, update_expr, ...)
            tx.commit()
    """

    def __init__(
        self,
        dynamodb_client: Any,
        table_prefix: str = "",
    ) -> None:
        self._client = dynamodb_client
        self._table_prefix = table_prefix
        self._operations: list[dict[str, Any]] = []

    def __enter__(self) -> TransactionHelper:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        # Don't auto-commit; caller must call commit() explicitly.
        self._operations.clear()

    @property
    def operation_count(self) -> int:
        return len(self._operations)

    def add_put(
        self,
        table_name: str,
        item: dict[str, Any],
        condition_expression: str | None = None,
    ) -> None:
        """Add a Put operation to the transaction."""
        self._check_limit()
        op: dict[str, Any] = {
            "Put": {
                "TableName": f"{self._table_prefix}{table_name}",
                "Item": self._serialize_item(item),
            }
        }
        if condition_expression:
            op["Put"]["ConditionExpression"] = condition_expression
        self._operations.append(op)

    def add_update(
        self,
        table_name: str,
        key: dict[str, Any],
        update_expression: str,
        expression_attribute_names: dict[str, str] | None = None,
        expression_attribute_values: dict[str, Any] | None = None,
        condition_expression: str | None = None,
    ) -> None:
        """Add an Update operation to the transaction."""
        self._check_limit()
        op: dict[str, Any] = {
            "Update": {
                "TableName": f"{self._table_prefix}{table_name}",
                "Key": self._serialize_item(key),
                "UpdateExpression": update_expression,
            }
        }
        if expression_attribute_names:
            op["Update"]["ExpressionAttributeNames"] = expression_attribute_names
        if expression_attribute_values:
            op["Update"]["ExpressionAttributeValues"] = self._serialize_item(
                expression_attribute_values
            )
        if condition_expression:
            op["Update"]["ConditionExpression"] = condition_expression
        self._operations.append(op)

    def add_delete(
        self,
        table_name: str,
        key: dict[str, Any],
        condition_expression: str | None = None,
    ) -> None:
        """Add a Delete operation to the transaction."""
        self._check_limit()
        op: dict[str, Any] = {
            "Delete": {
                "TableName": f"{self._table_prefix}{table_name}",
                "Key": self._serialize_item(key),
            }
        }
        if condition_expression:
            op["Delete"]["ConditionExpression"] = condition_expression
        self._operations.append(op)

    def add_condition_check(
        self,
        table_name: str,
        key: dict[str, Any],
        condition_expression: str,
        expression_attribute_names: dict[str, str] | None = None,
        expression_attribute_values: dict[str, Any] | None = None,
    ) -> None:
        """Add a ConditionCheck operation to the transaction."""
        self._check_limit()
        op: dict[str, Any] = {
            "ConditionCheck": {
                "TableName": f"{self._table_prefix}{table_name}",
                "Key": self._serialize_item(key),
                "ConditionExpression": condition_expression,
            }
        }
        if expression_attribute_names:
            op["ConditionCheck"]["ExpressionAttributeNames"] = (
                expression_attribute_names
            )
        if expression_attribute_values:
            op["ConditionCheck"]["ExpressionAttributeValues"] = self._serialize_item(
                expression_attribute_values
            )
        self._operations.append(op)

    def commit(self) -> None:
        """Execute all collected operations atomically.

        Raises TransactionConflictError if the transaction is cancelled.
        Raises DataAccessError for other DynamoDB errors.
        """
        if not self._operations:
            return

        start = time.monotonic()
        try:
            self._client.transact_write_items(TransactItems=self._operations)
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code == "TransactionCanceledException":
                reasons = exc.response.get("CancellationReasons", [])
                raise TransactionConflictError(
                    f"Transaction cancelled: {len(self._operations)} operations",
                    operation="transact_write",
                    cancellation_reasons=reasons,
                ) from exc
            raise DataAccessError(
                f"Transaction failed: {exc.response['Error'].get('Message', str(exc))}",
                operation="transact_write",
            ) from exc
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.debug(
                "TransactWriteItems: %d ops (%.2fms)",
                len(self._operations),
                elapsed_ms,
            )
            self._operations.clear()

    def _check_limit(self) -> None:
        if len(self._operations) >= MAX_TRANSACTION_ITEMS:
            raise ValueError(
                f"Transaction cannot exceed {MAX_TRANSACTION_ITEMS} operations "
                f"(currently {len(self._operations)})"
            )

    @staticmethod
    def _serialize_item(item: dict[str, Any]) -> dict[str, Any]:
        """Convert Python types to DynamoDB-compatible types for the low-level client.

        The TransactWriteItems API uses the low-level client which requires
        DynamoDB type descriptors (e.g. {"S": "value"}).
        """
        serialized: dict[str, Any] = {}
        for k, v in item.items():
            serialized[k] = TransactionHelper._serialize_value(v)
        return serialized

    @staticmethod
    def _serialize_value(value: Any) -> dict[str, Any]:
        """Serialize a single value for DynamoDB low-level format."""
        if isinstance(value, str):
            return {"S": value}
        if isinstance(value, bool):
            return {"BOOL": value}
        if isinstance(value, decimal.Decimal):
            return {"N": str(value)}
        if isinstance(value, (int, float)):
            return {"N": str(value)}
        if value is None:
            return {"NULL": True}
        if isinstance(value, bytes):
            return {"B": value}
        if isinstance(value, set):
            if all(isinstance(i, str) for i in value):
                return {"SS": sorted(value)}
            if all(isinstance(i, (int, float, decimal.Decimal)) for i in value):
                return {"NS": [str(i) for i in value]}
            raise TypeError(f"Unsupported set element types in: {value!r}")
        if isinstance(value, dict):
            return {"M": TransactionHelper._serialize_item(value)}
        if isinstance(value, list):
            return {"L": [TransactionHelper._serialize_value(i) for i in value]}
        raise TypeError(
            f"Cannot serialize type {type(value).__name__} for DynamoDB: {value!r}"
        )
