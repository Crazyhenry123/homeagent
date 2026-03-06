"""Agent template management — CRUD for dynamic agent type definitions.

Templates replace the hardcoded AGENT_TYPES dict, allowing admins to create
new agent types with custom system prompts at runtime.
"""

from datetime import datetime, timezone

from ulid import ULID

from app.models.dynamo import get_table


# Built-in agent definitions that get seeded as templates on startup
_BUILTIN_AGENTS = {
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
        "system_prompt": "",
        "required_permissions": ["health_data", "medical_records"],
        "is_default": True,
    },
    "logistics_assistant": {
        "name": "Logistics Assistant",
        "description": "Email drafting and scheduling assistance",
        "default_config": {"draft_only": True},
        "system_prompt": "",
        "required_permissions": ["email_access", "calendar_access"],
        "is_default": True,
    },
    "shopping_assistant": {
        "name": "Shopping Assistant",
        "description": "Product search and recommendations",
        "default_config": {},
        "system_prompt": "",
        "required_permissions": [],
        "is_default": False,
    },
}


def seed_builtin_templates(app) -> None:
    """Create template entries for each built-in agent if they don't exist.

    Called during app initialization. Uses a standalone DynamoDB resource
    (not the Flask request-scoped one) since this runs outside requests.
    """
    import boto3

    region = app.config["AWS_REGION"]
    endpoint_url = app.config.get("DYNAMODB_ENDPOINT")
    kwargs = {"region_name": region}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    dynamodb = boto3.resource("dynamodb", **kwargs)
    table = dynamodb.Table("AgentTemplates")

    now = datetime.now(timezone.utc).isoformat()

    for agent_type, info in _BUILTIN_AGENTS.items():
        # Check if template already exists for this agent_type via GSI
        result = table.query(
            IndexName="agent_type-index",
            KeyConditionExpression="agent_type = :at",
            ExpressionAttributeValues={":at": agent_type},
            Limit=1,
        )
        if result.get("Items"):
            # Clean up duplicates: keep only the first, delete the rest
            all_for_type = table.query(
                IndexName="agent_type-index",
                KeyConditionExpression="agent_type = :at",
                ExpressionAttributeValues={":at": agent_type},
            ).get("Items", [])
            if len(all_for_type) > 1:
                for dup in all_for_type[1:]:
                    table.delete_item(Key={"template_id": dup["template_id"]})
            continue

        # Use a deterministic template_id to prevent race condition duplicates
        template_id = f"builtin-{agent_type}"
        try:
            table.put_item(
                Item={
                    "template_id": template_id,
                    "agent_type": agent_type,
                    "name": info["name"],
                    "description": info["description"],
                    "system_prompt": info["system_prompt"],
                    "default_config": info["default_config"],
                    "required_permissions": info.get("required_permissions", []),
                    "is_default": info.get("is_default", False),
                "is_builtin": True,
                "available_to": "all",
                "created_by": "system",
                "created_at": now,
                "updated_at": now,
                },
                ConditionExpression="attribute_not_exists(template_id)",
            )
        except Exception:
            pass  # Already exists (race condition with another worker)


def list_templates() -> list[dict]:
    """Return all agent templates."""
    table = get_table("AgentTemplates")
    result = table.scan()
    return result.get("Items", [])


def get_template(template_id: str) -> dict | None:
    """Get a single template by its primary key."""
    table = get_table("AgentTemplates")
    return table.get_item(Key={"template_id": template_id}).get("Item")


def get_template_by_type(agent_type: str) -> dict | None:
    """Look up a template by its agent_type slug via GSI."""
    table = get_table("AgentTemplates")
    result = table.query(
        IndexName="agent_type-index",
        KeyConditionExpression="agent_type = :at",
        ExpressionAttributeValues={":at": agent_type},
        Limit=1,
    )
    items = result.get("Items", [])
    return items[0] if items else None


def create_template(
    name: str,
    agent_type: str,
    description: str,
    system_prompt: str,
    default_config: dict | None = None,
    available_to: str | list[str] = "all",
    created_by: str = "system",
) -> dict:
    """Create a new agent template.

    Raises ValueError if agent_type already exists.
    """
    if get_template_by_type(agent_type):
        raise ValueError(f"Agent type already exists: {agent_type}")

    table = get_table("AgentTemplates")
    now = datetime.now(timezone.utc).isoformat()
    template_id = str(ULID())

    item = {
        "template_id": template_id,
        "agent_type": agent_type,
        "name": name,
        "description": description,
        "system_prompt": system_prompt,
        "default_config": default_config or {},
        "is_builtin": False,
        "available_to": available_to,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
    table.put_item(Item=item)
    return item


def update_template(template_id: str, **updates) -> dict | None:
    """Partial update of a template. Returns updated item or None if not found."""
    template = get_template(template_id)
    if not template:
        return None

    allowed_fields = {
        "name", "description", "system_prompt", "default_config", "available_to",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}
    if not filtered:
        return template

    filtered["updated_at"] = datetime.now(timezone.utc).isoformat()

    update_parts = []
    attr_names = {}
    attr_values = {}
    for i, (key, value) in enumerate(filtered.items()):
        placeholder = f"#k{i}"
        val_placeholder = f":v{i}"
        update_parts.append(f"{placeholder} = {val_placeholder}")
        attr_names[placeholder] = key
        attr_values[val_placeholder] = value

    table = get_table("AgentTemplates")
    result = table.update_item(
        Key={"template_id": template_id},
        UpdateExpression="SET " + ", ".join(update_parts),
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
        ReturnValues="ALL_NEW",
    )
    return result.get("Attributes")


def delete_template(template_id: str) -> bool:
    """Delete a template. Rejects built-in templates. Cascades to AgentConfigs.

    Returns True if deleted, raises ValueError if built-in.
    """
    template = get_template(template_id)
    if not template:
        return False

    if template.get("is_builtin"):
        raise ValueError("Cannot delete built-in agent template")

    agent_type = template["agent_type"]

    # Cascade-delete all AgentConfigs referencing this agent_type
    configs_table = get_table("AgentConfigs")
    result = configs_table.scan(
        FilterExpression="agent_type = :at",
        ExpressionAttributeValues={":at": agent_type},
    )
    for item in result.get("Items", []):
        configs_table.delete_item(
            Key={"user_id": item["user_id"], "agent_type": item["agent_type"]}
        )

    # Delete the template itself
    table = get_table("AgentTemplates")
    table.delete_item(Key={"template_id": template_id})
    return True


def get_default_agent_types() -> list[str]:
    """Return agent_type slugs for all agents marked as default."""
    return [
        agent_type
        for agent_type, info in _BUILTIN_AGENTS.items()
        if info.get("is_default", False)
    ]


def get_available_templates(user_id: str) -> list[dict]:
    """Return templates available to a specific user.

    A template is available if available_to == "all" or user_id is in the list.
    """
    all_templates = list_templates()
    result = []
    for t in all_templates:
        avail = t.get("available_to", "all")
        if avail == "all" or (isinstance(avail, list) and user_id in avail):
            result.append(t)
    return result
