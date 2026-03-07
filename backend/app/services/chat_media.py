"""Service for chat media (image) upload management with S3 presigned URLs."""

import time
from datetime import datetime, timezone

import boto3
from flask import current_app
from ulid import ULID

from app.models.dynamo import get_table

CHAT_MEDIA_MAX_PER_MESSAGE = 5
UPLOAD_TTL_SECONDS = 3600  # 1 hour for orphaned uploads
PRESIGNED_URL_EXPIRY = 300  # 5 minutes for presigned upload URLs


def _get_s3_client() -> "boto3.client":
    kwargs = {"region_name": current_app.config["AWS_REGION"]}
    endpoint = current_app.config.get("S3_ENDPOINT")
    if endpoint:
        kwargs["endpoint_url"] = endpoint
        kwargs["config"] = boto3.session.Config(s3={"addressing_style": "path"})
    return boto3.client("s3", **kwargs)


def _get_presigned_s3_client() -> "boto3.client":
    """Get S3 client configured for presigned URL generation.

    Uses S3_PRESIGNED_ENDPOINT if set (for local dev where the Docker-internal
    hostname differs from the externally-reachable address), falling back to
    the regular S3 client.
    """
    presigned_endpoint = current_app.config.get("S3_PRESIGNED_ENDPOINT")
    if presigned_endpoint:
        if not presigned_endpoint.startswith(("http://", "https://")):
            raise ValueError(f"S3_PRESIGNED_ENDPOINT must be an HTTP(S) URL, got: {presigned_endpoint}")
        return boto3.client(
            "s3",
            region_name=current_app.config["AWS_REGION"],
            endpoint_url=presigned_endpoint,
            config=boto3.session.Config(s3={"addressing_style": "path"}),
        )
    return _get_s3_client()


def create_upload(
    user_id: str, content_type: str, file_size: int
) -> dict:
    """Create a chat media upload record and return a presigned PUT URL.

    Raises ValueError for invalid content type or file size.
    """
    allowed_types = current_app.config["CHAT_MEDIA_ALLOWED_TYPES"]
    is_audio = content_type.startswith("audio/")
    max_size = (
        current_app.config["CHAT_MEDIA_AUDIO_MAX_SIZE"]
        if is_audio
        else current_app.config["CHAT_MEDIA_MAX_SIZE"]
    )
    if content_type not in allowed_types:
        raise ValueError(
            f"Invalid content type: {content_type}. "
            f"Allowed: {', '.join(sorted(allowed_types))}"
        )
    if file_size > max_size:
        raise ValueError(
            f"File size {file_size} exceeds maximum of {max_size} bytes"
        )
    if file_size <= 0:
        raise ValueError("File size must be positive")

    table = get_table("ChatMedia")
    now = datetime.now(timezone.utc)
    media_id = str(ULID())

    # Derive extension and filename prefix from content type
    ext = content_type.split("/")[-1]
    if ext == "jpeg":
        ext = "jpg"
    prefix = "audio" if is_audio else "image"
    s3_key = f"chat-media/{user_id}/{media_id}/{prefix}.{ext}"

    item = {
        "media_id": media_id,
        "user_id": user_id,
        "s3_key": s3_key,
        "content_type": content_type,
        "file_size": file_size,
        "status": "pending",
        "uploaded_at": now.isoformat(),
        "expires_at": int(time.time()) + UPLOAD_TTL_SECONDS,
    }
    table.put_item(Item=item)

    # Generate presigned PUT URL (use presigned client for correct hostname)
    bucket = current_app.config["S3_HEALTH_DOCUMENTS_BUCKET"]
    s3 = _get_presigned_s3_client()
    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": s3_key,
            "ContentType": content_type,
        },
        ExpiresIn=PRESIGNED_URL_EXPIRY,
    )

    return {"media_id": media_id, "upload_url": upload_url}


def upload_file_to_s3(media_id: str, file_data: bytes, content_type: str) -> None:
    """Upload file bytes directly to S3 for a given media_id."""
    item = get_media(media_id)
    if not item:
        raise ValueError(f"Media not found: {media_id}")

    bucket = current_app.config["S3_HEALTH_DOCUMENTS_BUCKET"]
    s3 = _get_s3_client()
    s3.put_object(
        Bucket=bucket,
        Key=item["s3_key"],
        Body=file_data,
        ContentType=content_type,
    )


def get_media(media_id: str) -> dict | None:
    """Get a chat media record by ID."""
    table = get_table("ChatMedia")
    result = table.get_item(Key={"media_id": media_id})
    return result.get("Item")


def mark_attached(media_id: str) -> bool:
    """Mark a media item as attached to a message. Returns True if successful."""
    table = get_table("ChatMedia")
    try:
        table.update_item(
            Key={"media_id": media_id},
            UpdateExpression="SET #s = :attached REMOVE expires_at",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":attached": "attached"},
            ConditionExpression="attribute_exists(media_id)",
        )
        return True
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return False


def resolve_media_for_message(
    media_ids: list[str], user_id: str
) -> list[dict]:
    """Resolve media IDs to S3 URIs for Bedrock. Validates ownership.

    Returns list of {s3_uri, content_type, format} dicts.
    Raises ValueError if any media_id is invalid or doesn't belong to user.
    """
    if len(media_ids) > CHAT_MEDIA_MAX_PER_MESSAGE:
        raise ValueError(
            f"Too many images: {len(media_ids)}, max is {CHAT_MEDIA_MAX_PER_MESSAGE}"
        )

    bucket = current_app.config["S3_HEALTH_DOCUMENTS_BUCKET"]
    s3 = _get_s3_client()
    results = []

    validated_ids: list[str] = []

    for mid in media_ids:
        item = get_media(mid)
        if not item:
            raise ValueError(f"Media not found: {mid}")
        if item["user_id"] != user_id:
            raise ValueError(f"Media not owned by user: {mid}")

        # Verify the file was actually uploaded to S3
        try:
            s3.head_object(Bucket=bucket, Key=item["s3_key"])
        except Exception:
            raise ValueError(f"Media not yet uploaded: {mid}")

        # Determine media type and format
        is_audio = item["content_type"].startswith("audio/")
        fmt = item["content_type"].split("/")[-1]
        if fmt == "jpg":
            fmt = "jpeg"

        results.append(
            {
                "s3_uri": f"s3://{bucket}/{item['s3_key']}",
                "content_type": item["content_type"],
                "format": fmt,
                "media_type": "audio" if is_audio else "image",
            }
        )
        validated_ids.append(mid)

    # Mark all media as attached only after all validations pass
    for mid in validated_ids:
        mark_attached(mid)

    return results
