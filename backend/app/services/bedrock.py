import logging
from typing import Generator

import boto3
from flask import current_app

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "bedrock-runtime", region_name=current_app.config["AWS_REGION"]
        )
    return _client


def build_image_content_block(img: dict) -> dict:
    """Build a single Bedrock image content block from a media dict.

    Downloads image bytes from S3 so the block works with both the raw
    Bedrock converse API and the Strands SDK (which expects "bytes" source).

    Args:
        img: Dict with "s3_uri", "content_type", and "format" keys.
    """
    from app.services.chat_media import _get_s3_client

    # Parse s3://bucket/key
    s3_uri = img["s3_uri"]
    parts = s3_uri.replace("s3://", "").split("/", 1)
    bucket, key = parts[0], parts[1]

    s3 = _get_s3_client()
    resp = s3.get_object(Bucket=bucket, Key=key)
    image_bytes = resp["Body"].read()

    return {
        "image": {
            "format": img["format"],
            "source": {
                "bytes": image_bytes,
            },
        }
    }


def _build_content_blocks(
    text: str, images: list[dict] | None = None, is_last_user: bool = False
) -> list[dict]:
    """Build Bedrock content blocks, optionally with images on the last user message."""
    blocks: list[dict] = []
    if is_last_user and images:
        blocks.extend(build_image_content_block(img) for img in images)
    blocks.append({"text": text})
    return blocks


def stream_chat(
    messages: list[dict],
    system_prompt: str | None = None,
    images: list[dict] | None = None,
) -> Generator[dict, None, None]:
    """Stream a chat completion from Bedrock Claude.

    Args:
        messages: List of {"role": "user"|"assistant", "content": str}
        system_prompt: Optional system prompt override.
        images: Optional list of {"s3_uri", "content_type", "format"} for the
                last user message.

    Yields:
        Dicts with type "text_delta" (partial text) or "message_done" (final metadata).
    """
    client = _get_client()
    model_id = current_app.config["BEDROCK_MODEL_ID"]

    if system_prompt is None:
        system_prompt = current_app.config["SYSTEM_PROMPT"]

    # Build converse API messages
    converse_messages = []
    last_idx = len(messages) - 1
    for i, msg in enumerate(messages):
        is_last_user = i == last_idx and msg["role"] == "user"
        converse_messages.append(
            {
                "role": msg["role"],
                "content": _build_content_blocks(
                    msg["content"], images, is_last_user
                ),
            }
        )

    kwargs = {
        "modelId": model_id,
        "messages": converse_messages,
        "system": [{"text": system_prompt}],
        "inferenceConfig": {
            "maxTokens": 4096,
            "temperature": 0.7,
        },
    }

    try:
        response = client.converse_stream(**kwargs)
    except Exception:
        logger.exception("Bedrock converse_stream call failed")
        yield {
            "type": "error",
            "content": "Failed to connect to AI service. Please try again.",
        }
        return

    full_text = ""
    input_tokens = 0
    output_tokens = 0

    for event in response["stream"]:
        if "contentBlockDelta" in event:
            delta = event["contentBlockDelta"]["delta"]
            if "text" in delta:
                chunk = delta["text"]
                full_text += chunk
                yield {"type": "text_delta", "content": chunk}

        elif "metadata" in event:
            usage = event["metadata"].get("usage", {})
            input_tokens = usage.get("inputTokens", 0)
            output_tokens = usage.get("outputTokens", 0)

    yield {
        "type": "message_done",
        "content": full_text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
