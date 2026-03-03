from datetime import datetime, timezone

from app.models.dynamo import get_table

# Default available agent types and their metadata
AGENT_TYPES = {
    "health_advisor": {
        "name": "Health Advisor",
        "description": (
            "Comprehensive family health companion with access to medical records, "
            "health observations, and conversation history. Provides age-specific "
            "guidance for pediatric and geriatric care, tracks health patterns, "
            "and generates personalized wellness recommendations."
        ),
        "default_config": {
            "safety_disclaimers": True,
            "web_search_enabled": False,
            "conversation_mining_enabled": True,
            "observation_tracking_enabled": True,
        },
    },
    "logistics_assistant": {
        "name": "Logistics Assistant",
        "description": "Email drafting and scheduling assistance",
        "default_config": {
            "draft_only": True,
        },
    },
    "shopping_assistant": {
        "name": "Shopping Assistant",
        "description": "Product search and recommendations",
        "default_config": {},
    },
}


def get_available_agent_types() -> dict:
    """Return all available agent types with their metadata."""
    return AGENT_TYPES


def get_agent_configs(user_id: str) -> list[dict]:
    """Get all agent configs for a user."""
    table = get_table("AgentConfigs")
    result = table.query(
        KeyConditionExpression="user_id = :uid",
        ExpressionAttributeValues={":uid": user_id},
    )
    return result.get("Items", [])


def get_agent_config(user_id: str, agent_type: str) -> dict | None:
    """Get a specific agent config for a user."""
    table = get_table("AgentConfigs")
    item = table.get_item(
        Key={"user_id": user_id, "agent_type": agent_type}
    ).get("Item")
    return item


def put_agent_config(
    user_id: str,
    agent_type: str,
    enabled: bool = True,
    config: dict | None = None,
) -> dict:
    """Create or update an agent config for a user.

    Raises ValueError if agent_type is not recognized.
    """
    if agent_type not in AGENT_TYPES:
        raise ValueError(f"Unknown agent type: {agent_type}")

    table = get_table("AgentConfigs")
    now = datetime.now(timezone.utc).isoformat()

    default_config = AGENT_TYPES[agent_type]["default_config"]
    merged_config = {**default_config, **(config or {})}

    item = {
        "user_id": user_id,
        "agent_type": agent_type,
        "enabled": enabled,
        "config": merged_config,
        "updated_at": now,
    }
    table.put_item(Item=item)
    return item


def delete_agent_config(user_id: str, agent_type: str) -> bool:
    """Delete an agent config. Returns True if it existed."""
    table = get_table("AgentConfigs")
    try:
        table.delete_item(
            Key={"user_id": user_id, "agent_type": agent_type},
            ConditionExpression="attribute_exists(user_id)",
        )
        return True
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return False
