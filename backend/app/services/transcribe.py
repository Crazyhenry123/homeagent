"""Service for audio transcription using AWS Transcribe.

In local dev (S3_ENDPOINT set), audio lives in MinIO which AWS Transcribe
can't access. We copy the file to a real S3 temp bucket for transcription,
then clean up. In production, the audio is already in real S3.
"""

import json
import logging
import time
import uuid

import boto3
from flask import current_app

logger = logging.getLogger(__name__)

TRANSCRIPTION_TIMEOUT_SECONDS = 120
# Temporary bucket in real AWS for transcription in local dev
_TRANSCRIBE_TEMP_BUCKET = "homeagent-transcribe-temp"


def _get_transcribe_client():
    return boto3.client(
        "transcribe", region_name=current_app.config["AWS_REGION"]
    )


def _get_local_s3_client():
    """S3 client for local MinIO."""
    endpoint = current_app.config.get("S3_ENDPOINT")
    return boto3.client(
        "s3",
        region_name=current_app.config["AWS_REGION"],
        endpoint_url=endpoint,
        aws_access_key_id=current_app.config.get("S3_ACCESS_KEY_ID", "local"),
        aws_secret_access_key=current_app.config.get(
            "S3_SECRET_ACCESS_KEY", "locallocal"
        ),
        config=boto3.session.Config(s3={"addressing_style": "path"}),
    )


def _get_real_s3_client():
    """S3 client for real AWS (uses default credentials chain)."""
    return boto3.client(
        "s3", region_name=current_app.config["AWS_REGION"]
    )


def _ensure_temp_bucket(s3_client: "boto3.client") -> None:
    """Create the temp transcription bucket if it doesn't exist."""
    try:
        s3_client.head_bucket(Bucket=_TRANSCRIBE_TEMP_BUCKET)
    except Exception:
        try:
            region = current_app.config["AWS_REGION"]
            params: dict = {"Bucket": _TRANSCRIBE_TEMP_BUCKET}
            if region != "us-east-1":
                params["CreateBucketConfiguration"] = {
                    "LocationConstraint": region
                }
            s3_client.create_bucket(**params)
            logger.info("Created temp transcription bucket %s", _TRANSCRIBE_TEMP_BUCKET)
        except Exception:
            logger.debug(
                "Temp bucket creation failed (may already exist)", exc_info=True
            )


def transcribe_audio(s3_uri: str) -> str:
    """Transcribe audio from an S3 URI using AWS Transcribe.

    Args:
        s3_uri: S3 URI of the audio file (e.g. s3://bucket/key).

    Returns:
        Transcribed text string.

    Raises:
        RuntimeError: If transcription job fails or times out.
    """
    is_local = bool(current_app.config.get("S3_ENDPOINT"))
    parts = s3_uri.replace("s3://", "").split("/", 1)
    source_bucket, source_key = parts[0], parts[1]

    client = _get_transcribe_client()
    real_s3 = _get_real_s3_client()
    job_name = f"homeagent-{uuid.uuid4().hex[:12]}"

    # In local dev, copy audio from MinIO to a real S3 bucket
    temp_key = None
    if is_local:
        local_s3 = _get_local_s3_client()
        obj = local_s3.get_object(Bucket=source_bucket, Key=source_key)
        audio_bytes = obj["Body"].read()

        _ensure_temp_bucket(real_s3)
        temp_key = f"audio/{job_name}.wav"
        real_s3.put_object(
            Bucket=_TRANSCRIBE_TEMP_BUCKET,
            Key=temp_key,
            Body=audio_bytes,
            ContentType="audio/wav",
        )
        transcribe_uri = f"s3://{_TRANSCRIBE_TEMP_BUCKET}/{temp_key}"
        output_bucket = _TRANSCRIBE_TEMP_BUCKET
    else:
        transcribe_uri = s3_uri
        output_bucket = source_bucket

    output_key = f"transcribe-output/{job_name}.json"

    try:
        client.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": transcribe_uri},
            IdentifyLanguage=True,
            LanguageOptions=["en-US", "zh-CN"],
            OutputBucketName=output_bucket,
            OutputKey=output_key,
        )

        # Poll until complete with timeout
        deadline = time.monotonic() + TRANSCRIPTION_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            resp = client.get_transcription_job(
                TranscriptionJobName=job_name
            )
            status = resp["TranscriptionJob"]["TranscriptionJobStatus"]

            if status == "COMPLETED":
                break
            elif status == "FAILED":
                reason = resp["TranscriptionJob"].get(
                    "FailureReason", "Unknown"
                )
                logger.error(
                    "Transcription job %s failed: %s", job_name, reason
                )
                raise RuntimeError(f"Transcription failed: {reason}")

            time.sleep(1)
        else:
            logger.error(
                "Transcription job %s timed out after %ds",
                job_name,
                TRANSCRIPTION_TIMEOUT_SECONDS,
            )
            raise RuntimeError(
                f"Transcription timed out after {TRANSCRIPTION_TIMEOUT_SECONDS}s"
            )

        # Fetch the transcript JSON
        obj = real_s3.get_object(Bucket=output_bucket, Key=output_key)
        transcript_data = json.loads(obj["Body"].read().decode("utf-8"))
        text = transcript_data["results"]["transcripts"][0]["transcript"]

        if not text or not text.strip():
            raise RuntimeError("Transcription returned empty result")

        return text

    finally:
        # Clean up all temporary files
        for cleanup_key in [output_key, temp_key]:
            if cleanup_key:
                try:
                    real_s3.delete_object(
                        Bucket=output_bucket, Key=cleanup_key
                    )
                except Exception:
                    logger.debug(
                        "Failed to clean up %s/%s",
                        output_bucket,
                        cleanup_key,
                    )
        try:
            client.delete_transcription_job(TranscriptionJobName=job_name)
        except Exception:
            logger.debug("Failed to delete transcription job %s", job_name)
