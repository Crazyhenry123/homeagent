"""Service for health document metadata and S3 presigned URL management."""

from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from flask import current_app
from ulid import ULID

from app.models.dynamo import get_table

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/heic",
    "image/heif",
    "application/pdf",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


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
) -> dict:
    """Create document metadata in DynamoDB and return a presigned upload URL.

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

    table = get_table("HealthDocuments")
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


def get_download_url(user_id: str, document_id: str) -> dict | None:
    """Get document metadata and a presigned download URL."""
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


def list_documents(user_id: str) -> list[dict]:
    """List all documents for a user."""
    table = get_table("HealthDocuments")
    result = table.query(
        KeyConditionExpression=Key("user_id").eq(user_id),
    )
    return result.get("Items", [])


def delete_document(user_id: str, document_id: str) -> bool:
    """Delete a document's metadata and S3 object. Returns True if it existed."""
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


def delete_all_documents(user_id: str) -> None:
    """Delete all documents for a user (cascade delete)."""
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
