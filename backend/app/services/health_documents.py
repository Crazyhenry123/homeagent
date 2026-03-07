"""Service for health document metadata and file storage.

Supports pluggable storage via optional ``storage`` parameter.
When ``storage`` is None, falls back to DynamoDB + S3 (existing behavior).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import boto3
from boto3.dynamodb.conditions import Key
from flask import current_app
from ulid import ULID

from app.models.dynamo import get_table

if TYPE_CHECKING:
    from app.storage.base import StorageProvider

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/heic",
    "image/heif",
    "application/pdf",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

_COLLECTION = "health_documents_meta"


def _get_s3_client():
    kwargs = {"region_name": current_app.config["AWS_REGION"]}
    endpoint = current_app.config.get("S3_ENDPOINT")
    if endpoint:
        kwargs["endpoint_url"] = endpoint
        kwargs["config"] = boto3.session.Config(s3={"addressing_style": "path"})
    return boto3.client("s3", **kwargs)


def create_document_metadata(
    user_id: str,
    filename: str,
    content_type: str,
    file_size: int,
    uploaded_by: str,
    record_id: str | None = None,
    description: str = "",
    storage: StorageProvider | None = None,
) -> dict:
    """Create document metadata and return a presigned upload URL.

    When using an external storage provider, returns a backend-proxied
    upload endpoint instead of a presigned URL.

    Raises ValueError for invalid content type or file size.
    """
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(
            f"Invalid content type: {content_type}. "
            f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
        )
    if file_size > MAX_FILE_SIZE:
        raise ValueError(
            f"File size {file_size} exceeds maximum of {MAX_FILE_SIZE} bytes"
        )

    now = datetime.now(timezone.utc).isoformat()
    document_id = str(ULID())
    s3_key = f"health-documents/{user_id}/{document_id}/{filename}"

    item = {
        "user_id": user_id,
        "document_id": document_id,
        "filename": filename,
        "s3_key": s3_key,
        "content_type": content_type,
        "file_size": file_size,
        "uploaded_by": uploaded_by,
        "description": description,
        "uploaded_at": now,
    }
    if record_id:
        item["record_id"] = record_id

    if storage is not None:
        storage.put_record(user_id, _COLLECTION, document_id, item)
        # For external providers, the actual file upload goes through the
        # storage provider's put_file method. Return a backend upload URL.
        return {
            **item,
            "upload_url": f"/api/storage/upload/{document_id}",
            "upload_via": "backend",
        }

    table = get_table("HealthDocuments")
    table.put_item(Item=item)

    # Generate presigned PUT URL
    bucket = current_app.config["S3_HEALTH_DOCUMENTS_BUCKET"]
    s3 = _get_s3_client()
    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": s3_key,
            "ContentType": content_type,
        },
        ExpiresIn=3600,
    )

    return {**item, "upload_url": upload_url}


def get_download_url(
    user_id: str,
    document_id: str,
    storage: StorageProvider | None = None,
) -> dict | None:
    """Get document metadata and a download URL."""
    if storage is not None:
        item = storage.get_record(user_id, _COLLECTION, document_id)
        if not item:
            return None
        file_url = storage.get_file_url(user_id, item.get("s3_key", ""))
        return {**item, "download_url": file_url or ""}

    table = get_table("HealthDocuments")
    result = table.get_item(Key={"user_id": user_id, "document_id": document_id})
    item = result.get("Item")
    if not item:
        return None

    bucket = current_app.config["S3_HEALTH_DOCUMENTS_BUCKET"]
    s3 = _get_s3_client()
    download_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": item["s3_key"]},
        ExpiresIn=3600,
    )

    return {**item, "download_url": download_url}


def list_documents(
    user_id: str,
    storage: StorageProvider | None = None,
) -> list[dict]:
    """List all documents for a user."""
    if storage is not None:
        return storage.query_records(user_id, _COLLECTION)

    table = get_table("HealthDocuments")
    result = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id),
    )
    return result.get("Items", [])


def delete_document(
    user_id: str,
    document_id: str,
    storage: StorageProvider | None = None,
) -> bool:
    """Delete a document's metadata and file. Returns True if it existed."""
    if storage is not None:
        item = storage.get_record(user_id, _COLLECTION, document_id)
        if not item:
            return False
        s3_key = item.get("s3_key", "")
        if s3_key:
            storage.delete_file(user_id, s3_key)
        storage.delete_record(user_id, _COLLECTION, document_id)
        return True

    table = get_table("HealthDocuments")
    result = table.get_item(Key={"user_id": user_id, "document_id": document_id})
    item = result.get("Item")
    if not item:
        return False

    # Delete from S3
    bucket = current_app.config["S3_HEALTH_DOCUMENTS_BUCKET"]
    s3 = _get_s3_client()
    s3.delete_object(Bucket=bucket, Key=item["s3_key"])

    # Delete from DynamoDB
    table.delete_item(Key={"user_id": user_id, "document_id": document_id})
    return True


def delete_all_documents(
    user_id: str,
    storage: StorageProvider | None = None,
) -> None:
    """Delete all documents for a user (cascade delete)."""
    if storage is not None:
        docs = storage.query_records(user_id, _COLLECTION)
        for doc in docs:
            s3_key = doc.get("s3_key", "")
            if s3_key:
                storage.delete_file(user_id, s3_key)
        storage.delete_all_records(user_id, _COLLECTION)
        return

    table = get_table("HealthDocuments")
    result = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        ProjectionExpression="user_id, document_id, s3_key",
    )
    items = result.get("Items", [])
    if not items:
        return

    bucket = current_app.config.get("S3_HEALTH_DOCUMENTS_BUCKET")
    if bucket:
        s3 = _get_s3_client()
        for item in items:
            s3.delete_object(Bucket=bucket, Key=item["s3_key"])

    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(
                Key={"user_id": item["user_id"], "document_id": item["document_id"]}
            )
