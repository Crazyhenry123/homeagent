"""Background health observation extraction from chat conversations.

Supports pluggable storage via ``storage_provider_type`` parameter.
When the type is "local" (default), uses DynamoDB directly.
"""

from __future__ import annotations

import json
import logging

import boto3

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
You are a health data extraction assistant. Analyze the following conversation \
between a family member and an AI assistant. Extract any health-related \
observations mentioned.

For each observation, return a JSON object with:
- "category": one of "diet", "exercise", "sleep", "symptom", "mood", "general"
- "summary": a brief one-sentence summary
- "detail": additional detail (optional, empty string if none)
- "confidence": "high", "medium", or "low"

Return a JSON array of observations. If no health observations are found, \
return an empty array [].

IMPORTANT: Only return the JSON array, no other text.

User message:
{user_message}

Assistant response:
{assistant_response}
"""


def extract_health_observations(
    user_id: str,
    conversation_id: str,
    user_message: str,
    assistant_response: str,
    region: str,
    model_id: str,
    dynamodb_endpoint: str | None = None,
    storage_provider_type: str = "local",
) -> None:
    """Extract health observations from a chat exchange and save them.

    This runs in a background thread — failures are logged, never raised.
    Creates its own boto3 clients to avoid Flask request-context dependencies.

    When storage_provider_type is not "local", attempts to use the storage
    provider abstraction. Falls back to DynamoDB if the module is unavailable.
    """
    try:
        prompt = EXTRACTION_PROMPT.format(
            user_message=user_message,
            assistant_response=assistant_response,
        )

        bedrock = boto3.client("bedrock-runtime", region_name=region)
        response = bedrock.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 1024, "temperature": 0.0},
        )

        output_text = response["output"]["message"]["content"][0]["text"]
        observations = json.loads(output_text)

        if not isinstance(observations, list) or not observations:
            return

        from datetime import datetime, timezone

        from ulid import ULID

        valid_categories = {"diet", "exercise", "sleep", "symptom", "mood", "general"}
        now = datetime.now(timezone.utc).isoformat()

        # Try to use external storage provider for non-local types
        storage = None
        if storage_provider_type != "local":
            try:
                from app.storage.provider_factory import get_storage_provider

                storage = get_storage_provider(user_id)
            except (ImportError, Exception):
                logger.warning(
                    "Storage provider '%s' not available for background extraction, "
                    "falling back to DynamoDB",
                    storage_provider_type,
                )

        if storage is not None:
            for obs in observations:
                category = obs.get("category", "general")
                if category not in valid_categories:
                    category = "general"
                summary = obs.get("summary", "")
                if not summary:
                    continue

                observation_id = str(ULID())
                item = {
                    "user_id": user_id,
                    "observation_id": observation_id,
                    "category": category,
                    "summary": summary,
                    "detail": obs.get("detail", ""),
                    "confidence": obs.get("confidence", "medium"),
                    "source_conversation_id": conversation_id,
                    "observed_at": now,
                    "created_at": now,
                }
                storage.put_record(
                    user_id, "health_observations", observation_id, item
                )
        else:
            # Default: write directly to DynamoDB
            dynamo_kwargs: dict = {"region_name": region}
            if dynamodb_endpoint:
                dynamo_kwargs["endpoint_url"] = dynamodb_endpoint
            dynamodb = boto3.resource("dynamodb", **dynamo_kwargs)
            table = dynamodb.Table("HealthObservations")

            for obs in observations:
                category = obs.get("category", "general")
                if category not in valid_categories:
                    category = "general"

                summary = obs.get("summary", "")
                if not summary:
                    continue

                observation_id = str(ULID())
                item = {
                    "user_id": user_id,
                    "observation_id": observation_id,
                    "category": category,
                    "summary": summary,
                    "detail": obs.get("detail", ""),
                    "confidence": obs.get("confidence", "medium"),
                    "source_conversation_id": conversation_id,
                    "observed_at": now,
                    "created_at": now,
                }
                table.put_item(Item=item)

        logger.info(
            "Extracted %d health observations from conversation %s",
            len(observations),
            conversation_id,
        )

    except json.JSONDecodeError:
        logger.warning(
            "Health extraction returned non-JSON for conversation %s",
            conversation_id,
        )
    except Exception:
        logger.exception(
            "Health extraction failed for conversation %s", conversation_id
        )
