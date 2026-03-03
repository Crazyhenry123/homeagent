"""Background health observation extraction from chat conversations."""

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
) -> None:
    """Extract health observations from a chat exchange and save them.

    This runs in a background thread — failures are logged, never raised.
    Creates its own boto3 clients to avoid Flask request-context dependencies.
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

        # Build DynamoDB resource outside Flask context
        dynamo_kwargs = {"region_name": region}
        if dynamodb_endpoint:
            dynamo_kwargs["endpoint_url"] = dynamodb_endpoint
        dynamodb = boto3.resource("dynamodb", **dynamo_kwargs)
        table = dynamodb.Table("HealthObservations")

        from datetime import datetime, timezone

        from ulid import ULID

        valid_categories = {"diet", "exercise", "sleep", "symptom", "mood", "general"}
        now = datetime.now(timezone.utc).isoformat()

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
