"""Default storage provider backed by DynamoDB + S3."""

from __future__ import annotations

import logging
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key

from app.storage.base import (
    COLLECTION_HEALTH_AUDIT_LOG,
    COLLECTION_HEALTH_DOCUMENTS,
    COLLECTION_HEALTH_OBSERVATIONS,
    COLLECTION_HEALTH_RECORDS,
    StorageProvider,
)

logger = logging.getLogger(__name__)

# Map logical collection names to DynamoDB table names and key schemas.
_TABLE_MAP: dict[str, dict[str, Any]] = {
    COLLECTION_HEALTH_RECORDS: {
        "table": "HealthRecords",
        "pk": "user_id",
        "sk": "record_id",
    },
    COLLECTION_HEALTH_OBSERVATIONS: {
        "table": "HealthObservations",
        "pk": "user_id",
        "sk": "observation_id",
    },
    COLLECTION_HEALTH_DOCUMENTS: {
        "table": "HealthDocuments",
        "pk": "user_id",
        "sk": "document_id",
    },
    COLLECTION_HEALTH_AUDIT_LOG: {
        "table": "HealthAuditLog",
        "pk": "record_id",
        "sk": "audit_sk",
    },
}

# GSI lookup: (collection, index_name) → sort-key attribute used in that index.
_GSI_MAP: dict[tuple[str, str], str] = {
    (COLLECTION_HEALTH_RECORDS, "record_type-index"): "record_type",
    (COLLECTION_HEALTH_OBSERVATIONS, "category-index"): "category",
    (COLLECTION_HEALTH_AUDIT_LOG, "user-audit-index"): "created_at",
}


class LocalProvider(StorageProvider):
    """DynamoDB + S3 storage (the default / "local" provider)."""

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_table(self, collection: str) -> Any:
        """Return a DynamoDB Table resource.

        Tries Flask request-scoped helpers first, falls back to direct boto3
        so the provider works in background threads too.
        """
        table_info = _TABLE_MAP.get(collection)
        if not table_info:
            raise ValueError(f"Unknown collection: {collection}")

        table_name = table_info["table"]

        try:
            from flask import current_app, g  # noqa: WPS433

            if "dynamodb" not in g:
                endpoint_url = current_app.config.get("DYNAMODB_ENDPOINT")
                kwargs: dict[str, Any] = {
                    "region_name": current_app.config["AWS_REGION"]
                }
                if endpoint_url:
                    kwargs["endpoint_url"] = endpoint_url
                g.dynamodb = boto3.resource("dynamodb", **kwargs)
            return g.dynamodb.Table(table_name)
        except RuntimeError:
            # Outside Flask application context – use plain boto3.
            dynamodb = boto3.resource("dynamodb")
            return dynamodb.Table(table_name)

    def _get_s3_client(self) -> Any:
        """Return an S3 client."""
        try:
            from flask import current_app  # noqa: WPS433

            kwargs: dict[str, Any] = {
                "region_name": current_app.config["AWS_REGION"]
            }
            endpoint_url = current_app.config.get("S3_ENDPOINT")
            if endpoint_url:
                kwargs["endpoint_url"] = endpoint_url
            return boto3.client("s3", **kwargs)
        except RuntimeError:
            return boto3.client("s3")

    def _get_bucket_name(self) -> str:
        """Return the S3 bucket name for health documents."""
        try:
            from flask import current_app  # noqa: WPS433

            bucket = current_app.config.get("S3_HEALTH_DOCUMENTS_BUCKET")
            if bucket:
                return bucket
        except RuntimeError:
            pass
        import os

        return os.environ.get("S3_HEALTH_DOCUMENTS_BUCKET", "")

    @staticmethod
    def _key_info(collection: str) -> tuple[str, str]:
        """Return (pk_attr, sk_attr) for a collection."""
        info = _TABLE_MAP.get(collection)
        if not info:
            raise ValueError(f"Unknown collection: {collection}")
        return info["pk"], info["sk"]

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
            table = self._get_table(collection)
            kwargs: dict[str, Any] = {"Item": record}
            if condition_expression:
                kwargs["ConditionExpression"] = condition_expression
            table.put_item(**kwargs)
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
            table = self._get_table(collection)
            response = table.get_item(Key=key)
            return response.get("Item")
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
            table = self._get_table(collection)

            # Build key condition expression
            kce = None
            for attr, value in key_condition.items():
                if isinstance(value, tuple):
                    op, val = value
                    if op == "begins_with":
                        expr = Key(attr).begins_with(val)
                    elif op == "between":
                        expr = Key(attr).between(val[0], val[1])
                    elif op == "gte":
                        expr = Key(attr).gte(val)
                    elif op == "lte":
                        expr = Key(attr).lte(val)
                    else:
                        expr = Key(attr).eq(val)
                else:
                    expr = Key(attr).eq(value)
                kce = expr if kce is None else kce & expr

            kwargs: dict[str, Any] = {
                "KeyConditionExpression": kce,
                "ScanIndexForward": scan_forward,
            }
            if index_name:
                kwargs["IndexName"] = index_name
            if limit:
                kwargs["Limit"] = limit

            if filter_expression:
                fe = None
                for attr, value in filter_expression.items():
                    if isinstance(value, tuple):
                        op, val = value
                        if op == "eq":
                            expr = Attr(attr).eq(val)
                        elif op == "ne":
                            expr = Attr(attr).ne(val)
                        elif op == "contains":
                            expr = Attr(attr).contains(val)
                        else:
                            expr = Attr(attr).eq(val)
                    else:
                        expr = Attr(attr).eq(value)
                    fe = expr if fe is None else fe & expr
                kwargs["FilterExpression"] = fe

            response = table.query(**kwargs)
            return response.get("Items", [])
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
            table = self._get_table(collection)

            update_parts: list[str] = []
            attr_names: dict[str, str] = {}
            attr_values: dict[str, Any] = {}

            for idx, (attr, value) in enumerate(updates.items()):
                placeholder_name = f"#attr{idx}"
                placeholder_value = f":val{idx}"
                update_parts.append(f"{placeholder_name} = {placeholder_value}")
                attr_names[placeholder_name] = attr
                attr_values[placeholder_value] = value

            kwargs: dict[str, Any] = {
                "Key": key,
                "UpdateExpression": "SET " + ", ".join(update_parts),
                "ExpressionAttributeNames": attr_names,
                "ExpressionAttributeValues": attr_values,
                "ReturnValues": "ALL_NEW",
            }
            if condition_expression:
                kwargs["ConditionExpression"] = condition_expression

            response = table.update_item(**kwargs)
            return response.get("Attributes")
        except Exception:
            logger.exception("update_record failed for %s", collection)
            return None

    def delete_record(
        self,
        collection: str,
        key: dict[str, str],
    ) -> bool:
        try:
            table = self._get_table(collection)
            table.delete_item(Key=key)
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
            table = self._get_table(collection)
            pk_attr, sk_attr = self._key_info(collection)

            pk_name = list(partition_key.keys())[0]
            pk_value = partition_key[pk_name]

            response = table.query(
                KeyConditionExpression=Key(pk_name).eq(pk_value),
            )
            items = response.get("Items", [])
            count = 0
            with table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(
                        Key={pk_attr: item[pk_attr], sk_attr: item[sk_attr]}
                    )
                    count += 1
            return count
        except Exception:
            logger.exception("delete_all_records failed for %s", collection)
            return 0

    # ------------------------------------------------------------------
    # File operations (S3)
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
            s3 = self._get_s3_client()
            kwargs: dict[str, Any] = {
                "Bucket": self._get_bucket_name(),
                "Key": path,
                "Body": data,
            }
            if content_type:
                kwargs["ContentType"] = content_type
            if metadata:
                kwargs["Metadata"] = metadata
            s3.put_object(**kwargs)
            return path
        except Exception:
            logger.exception("put_file failed for %s", path)
            return None

    def get_file(self, path: str) -> bytes | None:
        try:
            s3 = self._get_s3_client()
            response = s3.get_object(
                Bucket=self._get_bucket_name(),
                Key=path,
            )
            return response["Body"].read()
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
            s3 = self._get_s3_client()
            url = s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._get_bucket_name(),
                    "Key": path,
                },
                ExpiresIn=expires_in,
            )
            return url
        except Exception:
            logger.exception("get_file_url failed for %s", path)
            return None

    def delete_file(self, path: str) -> bool:
        try:
            s3 = self._get_s3_client()
            s3.delete_object(
                Bucket=self._get_bucket_name(),
                Key=path,
            )
            return True
        except Exception:
            logger.exception("delete_file failed for %s", path)
            return False

    def delete_all_files(self, prefix: str) -> int:
        try:
            s3 = self._get_s3_client()
            bucket = self._get_bucket_name()
            response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
            objects = response.get("Contents", [])
            if not objects:
                return 0
            s3.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
            )
            return len(objects)
        except Exception:
            logger.exception("delete_all_files failed for prefix %s", prefix)
            return 0

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        try:
            table = self._get_table(COLLECTION_HEALTH_RECORDS)
            table.table_status  # noqa: B018 — triggers DescribeTable
            return {"ok": True, "provider": "local", "backend": "dynamodb+s3"}
        except Exception as exc:
            logger.exception("health_check failed")
            return {"ok": False, "provider": "local", "error": str(exc)}
