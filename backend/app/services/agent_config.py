from datetime import datetime, timezone

from app.models.dynamo import get_table
from app.services.agent_template import get_template_by_type, list_templates


def get_available_agent_types() -> dict:
    """Return all available agent types with their metadata.

    Queries the AgentTemplates table and returns a dict keyed by agent_type
    for backward compatibility with the existing admin UI.
    """
    templates = list_templates()
    result = {}
    for t in templates:
        result[t["agent_type"]] = {
            "name": t["name"],
            "description": t["description"],
            "default_config": t.get("default_config", {}),
            "required_permissions": t.get("required_permissions", []),
            "is_default": t.get("is_default", False),
        }
    return result


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

    Raises ValueError if agent_type is not recognized in AgentTemplates.
    """
    template = get_template_by_type(agent_type)
    if not template:
        raise ValueError(f"Unknown agent type: {agent_type}")

    table = get_table("AgentConfigs")
    now = datetime.now(timezone.utc).isoformat()

    default_config = template.get("default_config", {})
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
