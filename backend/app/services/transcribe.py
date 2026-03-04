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
    job_name = f"homeagent-{uuid.uuid4().hex[:12]}"

    client.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": s3_uri},
        IdentifyLanguage=True,
        LanguageOptions=["en-US", "zh-CN"],
    )

    # Poll until complete (short clips typically finish in a few seconds)
    while True:
        resp = client.get_transcription_job(TranscriptionJobName=job_name)
        status = resp["TranscriptionJob"]["TranscriptionJobStatus"]

        if status == "COMPLETED":
            transcript_uri = resp["TranscriptionJob"]["Transcript"][
                "TranscriptFileUri"
            ]
            break
        elif status == "FAILED":
            reason = resp["TranscriptionJob"].get("FailureReason", "Unknown")
            logger.error("Transcription job %s failed: %s", job_name, reason)
            raise RuntimeError(f"Transcription failed: {reason}")

        time.sleep(1)

    # Fetch the transcript JSON from the URI
    s3 = boto3.client("s3", region_name=current_app.config["AWS_REGION"])
    # Parse the transcript URI: https://s3.region.amazonaws.com/bucket/key
    # or s3://bucket/key format
    import urllib.parse

    parsed = urllib.parse.urlparse(transcript_uri)
    if parsed.scheme == "s3":
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
    else:
        # HTTPS URL: host is s3.region.amazonaws.com, path is /bucket/key
        path_parts = parsed.path.lstrip("/").split("/", 1)
        bucket = path_parts[0]
        key = path_parts[1] if len(path_parts) > 1 else ""

    obj = s3.get_object(Bucket=bucket, Key=key)
    transcript_data = json.loads(obj["Body"].read().decode("utf-8"))
    text = transcript_data["results"]["transcripts"][0]["transcript"]

    # Clean up the transcription job
    try:
        client.delete_transcription_job(TranscriptionJobName=job_name)
    except Exception:
        logger.warning("Failed to delete transcription job %s", job_name)

    return text
