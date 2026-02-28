import json
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


def stream_chat(
    messages: list[dict], system_prompt: str | None = None
) -> Generator[dict, None, None]:
    """Stream a chat completion from Bedrock Claude.

    Args:
        messages: List of {"role": "user"|"assistant", "content": str}
        system_prompt: Optional system prompt override.

    Yields:
        Dicts with type "text_delta" (partial text) or "message_done" (final metadata).
    """
    client = _get_client()
    model_id = current_app.config["BEDROCK_MODEL_ID"]

    if system_prompt is None:
        system_prompt = current_app.config["SYSTEM_PROMPT"]

    # Build converse API messages
    converse_messages = []
    for msg in messages:
        converse_messages.append(
            {
                "role": msg["role"],
                "content": [{"text": msg["content"]}],
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
