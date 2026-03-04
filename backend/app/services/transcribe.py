"""Service for audio transcription using AWS Transcribe."""

import json
import logging
import time
import uuid

import boto3
from flask import current_app

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "transcribe", region_name=current_app.config["AWS_REGION"]
        )
    return _client


def _get_s3_client():
    kwargs = {"region_name": current_app.config["AWS_REGION"]}
    endpoint = current_app.config.get("S3_ENDPOINT")
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client("s3", **kwargs)


def transcribe_audio(s3_uri: str) -> str:
    """Transcribe audio from an S3 URI using AWS Transcribe.

    Args:
        s3_uri: S3 URI of the audio file (e.g. s3://bucket/key).

    Returns:
        Transcribed text string.

    Raises:
        RuntimeError: If transcription job fails.
    """
    client = _get_client()
    bucket = current_app.config["S3_HEALTH_DOCUMENTS_BUCKET"]
    job_name = f"homeagent-{uuid.uuid4().hex[:12]}"
    output_key = f"transcribe-output/{job_name}.json"

    client.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": s3_uri},
        IdentifyLanguage=True,
        LanguageOptions=["en-US", "zh-CN"],
        OutputBucketName=bucket,
        OutputKey=output_key,
    )

    # Poll until complete (short clips typically finish in a few seconds)
    while True:
        resp = client.get_transcription_job(TranscriptionJobName=job_name)
        status = resp["TranscriptionJob"]["TranscriptionJobStatus"]

        if status == "COMPLETED":
            break
        elif status == "FAILED":
            reason = resp["TranscriptionJob"].get("FailureReason", "Unknown")
            logger.error("Transcription job %s failed: %s", job_name, reason)
            raise RuntimeError(f"Transcription failed: {reason}")

        time.sleep(1)

    # Fetch the transcript JSON from our own bucket
    s3 = _get_s3_client()
    obj = s3.get_object(Bucket=bucket, Key=output_key)
    transcript_data = json.loads(obj["Body"].read().decode("utf-8"))
    text = transcript_data["results"]["transcripts"][0]["transcript"]

    # Clean up transcript output and transcription job
    try:
        s3.delete_object(Bucket=bucket, Key=output_key)
    except Exception:
        logger.warning("Failed to delete transcript output %s", output_key)
    try:
        client.delete_transcription_job(TranscriptionJobName=job_name)
    except Exception:
        logger.warning("Failed to delete transcription job %s", job_name)

    return text
