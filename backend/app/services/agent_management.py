"""AgentCore Agent Management Client.

Replaces the current agent_config.py and agent_template.py services with a
unified class that manages agent templates (CRUD), per-user agent configs,
authorization, and dynamic sub-agent resolution via DynamoDB.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import boto3
from ulid import ULID

from app.models.agentcore import AgentConfig, AgentTemplate

logger = logging.getLogger(__name__)


class AgentManagementClient:
    """Manages agent templates and per-user agent configurations.

    Provides CRUD operations for AgentTemplates and AgentConfigs stored in
    DynamoDB, with authorization enforcement via the ``available_to`` field
    and cascade-delete semantics on template removal.
    """

    # Built-in agent definitions seeded on startup
    BUILTIN_TEMPLATES: dict[str, dict] = {
        "health_advisor": {
            "name": "Health Advisor",
            "description": (
                "Comprehensive family health companion with access to medical records, "
                "health observations, and conversation history. Provides age-specific "
                "guidance for pediatric and geriatric care, tracks health patterns, "
                "and generates personalized wellness recommendations."
            ),
            "system_prompt": "",
            "tool_server_ids": [],
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
            "system_prompt": "",
            "tool_server_ids": [],
            "default_config": {"draft_only": True},
        },
        "shopping_assistant": {
            "name": "Shopping Assistant",
            "description": "Product search and recommendations",
            "system_prompt": "",
            "tool_server_ids": [],
            "default_config": {},
        },
    }

    def __init__(self, region: str, endpoint_url: str | None = None) -> None:
        self._region = region
        self._endpoint_url = endpoint_url
        kwargs: dict = {"region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        self._dynamodb = boto3.resource("dynamodb", **kwargs)
        self._templates_table = self._dynamodb.Table("AgentTemplates")
        self._configs_table = self._dynamodb.Table("AgentConfigs")
        # Cache for resolved sub-agent tool IDs: {user_id: (tool_ids, timestamp)}
        self._tool_cache: dict[str, tuple[list[str], float]] = {}
        self._TOOL_CACHE_TTL: float = 60.0

    def seed_builtin_templates(self) -> list[AgentTemplate]:
        """Seed built-in templates on startup if they don't already exist.

        Checks for the existence of each built-in template by agent_type.
        Creates missing templates with predefined configuration. Does not
        overwrite existing templates.

        Returns the list of templates that were created (empty if all existed).
        """
        created: list[AgentTemplate] = []
        for agent_type, info in self.BUILTIN_TEMPLATES.items():
            existing = self.get_template_by_type(agent_type)
            if existing is not None:
                logger.info("Built-in template '%s' already exists, skipping", agent_type)
                continue

            template = self.create_agent_template(
                name=info["name"],
                agent_type=agent_type,
                description=info["description"],
                system_prompt=info["system_prompt"],
                tool_server_ids=info["tool_server_ids"],
                default_config=info.get("default_config"),
                available_to="all",
                is_builtin=True,
                created_by="system",
            )
            logger.info("Seeded built-in template: %s", agent_type)
            created.append(template)
        return created


    # ------------------------------------------------------------------
    # Template CRUD
    # ------------------------------------------------------------------

    def create_agent_template(
        self,
        name: str,
        agent_type: str,
        description: str,
        system_prompt: str,
        tool_server_ids: list[str] | None = None,
        default_config: dict | None = None,
        available_to: str | list[str] = "all",
        is_builtin: bool = False,
        created_by: str = "",
    ) -> AgentTemplate:
        """Create a new agent template with unique agent_type enforcement.

        Raises ``ValueError`` if *agent_type* already exists.
        """
        if self.get_template_by_type(agent_type) is not None:
            raise ValueError(f"Agent type already exists: {agent_type}")

        self._validate_available_to(available_to)

        now = datetime.now(timezone.utc).isoformat()
        template_id = str(ULID())

        template = AgentTemplate(
            template_id=template_id,
            agent_type=agent_type,
            name=name,
            description=description,
            system_prompt=system_prompt,
            tool_server_ids=tool_server_ids or [],
            default_config=default_config or {},
            is_builtin=is_builtin,
            available_to=available_to,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        template.validate()

        self._templates_table.put_item(Item=self._template_to_item(template))
        return template

    def get_template(self, template_id: str) -> AgentTemplate | None:
        """Get a single template by its primary key."""
        resp = self._templates_table.get_item(Key={"template_id": template_id})
        item = resp.get("Item")
        return self._item_to_template(item) if item else None

    def get_template_by_type(self, agent_type: str) -> AgentTemplate | None:
        """Look up a template by its agent_type slug via GSI."""
        result = self._templates_table.query(
            IndexName="agent_type-index",
            KeyConditionExpression="agent_type = :at",
            ExpressionAttributeValues={":at": agent_type},
            Limit=1,
        )
        items = result.get("Items", [])
        return self._item_to_template(items[0]) if items else None

    def list_templates(self) -> list[AgentTemplate]:
        """Return all agent templates."""
        result = self._templates_table.scan()
        return [self._item_to_template(item) for item in result.get("Items", [])]

    def get_available_templates(self, user_id: str) -> list[AgentTemplate]:
        """Return templates available to a specific user.

        A template is available if ``available_to == "all"`` or *user_id*
        is in the ``available_to`` list.
        """
        all_templates = self.list_templates()
        return [t for t in all_templates if self._is_available(t, user_id)]

    def update_template(self, template_id: str, **updates) -> AgentTemplate | None:
        """Partial update of a template. Returns updated template or None."""
        template = self.get_template(template_id)
        if template is None:
            return None

        allowed_fields = {
            "name", "description", "system_prompt", "default_config",
            "available_to", "tool_server_ids",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed_fields}
        if not filtered:
            return template

        if "available_to" in filtered:
            self._validate_available_to(filtered["available_to"])

        filtered["updated_at"] = datetime.now(timezone.utc).isoformat()

        update_parts = []
        attr_names: dict[str, str] = {}
        attr_values: dict = {}
        for i, (key, value) in enumerate(filtered.items()):
            placeholder = f"#k{i}"
            val_placeholder = f":v{i}"
            update_parts.append(f"{placeholder} = {val_placeholder}")
            attr_names[placeholder] = key
            attr_values[val_placeholder] = value

        result = self._templates_table.update_item(
            Key={"template_id": template_id},
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeNames=attr_names,
            ExpressionAttributeValues=attr_values,
            ReturnValues="ALL_NEW",
        )
        item = result.get("Attributes")
        if item is None:
            return None
        # Template changes (especially available_to) can affect any user's
        # resolved tool set, so clear the entire tool cache.
        self._tool_cache.clear()
        return self._item_to_template(item)

    def delete_template(self, template_id: str) -> bool:
        """Delete a template with built-in protection and cascade-delete.

        Built-in templates (``is_builtin == True``) cannot be deleted.
        All AgentConfigs referencing the deleted template's agent_type
        are cascade-deleted.

        Returns True if deleted, raises ``ValueError`` for built-in templates.
        """
        template = self.get_template(template_id)
        if template is None:
            return False

        if template.is_builtin:
            raise ValueError("Cannot delete built-in agent template")

        agent_type = template.agent_type

        # Cascade-delete all AgentConfigs referencing this agent_type
        result = self._configs_table.scan(
            FilterExpression="agent_type = :at",
            ExpressionAttributeValues={":at": agent_type},
        )
        for item in result.get("Items", []):
            self._configs_table.delete_item(
                Key={"user_id": item["user_id"], "agent_type": item["agent_type"]}
            )

        # Delete the template itself
        self._templates_table.delete_item(Key={"template_id": template_id})
        # Cascade-deleted configs invalidate tool resolution for affected users.
        self._tool_cache.clear()
        return True

    # ------------------------------------------------------------------
    # Per-User Agent Config
    # ------------------------------------------------------------------

    def get_user_agent_configs(self, user_id: str) -> list[AgentConfig]:
        """Return all agent configs for a user."""
        result = self._configs_table.query(
            KeyConditionExpression="user_id = :uid",
            ExpressionAttributeValues={":uid": user_id},
        )
        return [self._item_to_config(item) for item in result.get("Items", [])]

    def get_user_agent_config(self, user_id: str, agent_type: str) -> AgentConfig | None:
        """Return a single agent config for a user and agent_type, or None."""
        resp = self._configs_table.get_item(
            Key={"user_id": user_id, "agent_type": agent_type}
        )
        item = resp.get("Item")
        return self._item_to_config(item) if item else None

    def put_user_agent_config(
        self,
        user_id: str,
        agent_type: str,
        enabled: bool = True,
        config: dict | None = None,
        requesting_user_id: str | None = None,
        requesting_user_role: str | None = None,
    ) -> AgentConfig:
        """Create or update a per-user agent config.

        Validates that *agent_type* references a valid template and that
        the user is authorized via the template's ``available_to`` field.
        Merges the user-provided *config* with the template's
        ``default_config`` (user overrides take precedence).

        When *requesting_user_id* is provided and differs from *user_id*
        (cross-user modification), the requesting user must have
        ``requesting_user_role == "admin"``.  A non-admin cross-user
        attempt raises ``PermissionError``.

        Raises ``ValueError`` if the template does not exist or the user
        is not authorized.
        Raises ``PermissionError`` for non-admin cross-user modification.
        """
        # Cross-user admin check
        if (
            requesting_user_id is not None
            and requesting_user_id != user_id
            and requesting_user_role != "admin"
        ):
            raise PermissionError(
                "Admin role required for cross-user configuration"
            )

        template = self.get_template_by_type(agent_type)
        if template is None:
            raise ValueError(f"No template found for agent_type: {agent_type}")

        if not self._is_available(template, user_id):
            raise ValueError(
                f"User '{user_id}' is not authorized for agent_type: {agent_type}"
            )

        merged_config = {**template.default_config, **(config or {})}
        gateway_tool_id = f"gw-tool-{agent_type}"
        now = datetime.now(timezone.utc).isoformat()

        agent_config = AgentConfig(
            user_id=user_id,
            agent_type=agent_type,
            enabled=enabled,
            config=merged_config,
            gateway_tool_id=gateway_tool_id,
            updated_at=now,
        )

        self._configs_table.put_item(
            Item={
                "user_id": agent_config.user_id,
                "agent_type": agent_config.agent_type,
                "enabled": agent_config.enabled,
                "config": agent_config.config,
                "gateway_tool_id": agent_config.gateway_tool_id,
                "updated_at": agent_config.updated_at,
            }
        )
        self.invalidate_tool_cache(user_id)
        return agent_config

    def delete_user_agent_config(
        self,
        user_id: str,
        agent_type: str,
        requesting_user_id: str | None = None,
        requesting_user_role: str | None = None,
    ) -> bool:
        """Delete a per-user agent config.

        When *requesting_user_id* is provided and differs from *user_id*
        (cross-user modification), the requesting user must have
        ``requesting_user_role == "admin"``.  A non-admin cross-user
        attempt raises ``PermissionError``.

        Returns True if the config existed and was deleted, False if not found.
        Raises ``PermissionError`` for non-admin cross-user modification.
        """
        # Cross-user admin check
        if (
            requesting_user_id is not None
            and requesting_user_id != user_id
            and requesting_user_role != "admin"
        ):
            raise PermissionError(
                "Admin role required for cross-user configuration"
            )

        existing = self.get_user_agent_config(user_id, agent_type)
        if existing is None:
            return False

        self._configs_table.delete_item(
            Key={"user_id": user_id, "agent_type": agent_type}
        )
        self.invalidate_tool_cache(user_id)
        return True


    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    def is_user_authorized_for_template(
        self, user_id: str, template: AgentTemplate
    ) -> bool:
        """Check whether *user_id* is authorized to use *template*.

        Returns ``True`` if ``available_to == "all"`` or *user_id* appears
        in the ``available_to`` list.
        """
        return self._is_available(template, user_id)

    # ------------------------------------------------------------------
    # Dynamic Sub-Agent Resolution
    # ------------------------------------------------------------------

    def build_sub_agent_tool_ids(self, user_id: str) -> list[str]:
        """Resolve Gateway tool IDs for a user's enabled and authorized sub-agents.

        Queries the user's AgentConfigs, filters for ``enabled == True``,
        checks authorization against each template's ``available_to`` field,
        and returns the resolved ``gateway_tool_id`` values sorted by
        ``agent_type`` for deterministic ordering.

        Configs referencing missing templates are skipped with a warning.

        Results are cached per user with a 60-second TTL.  The cache is
        invalidated automatically when configs are created, updated, or
        deleted via :meth:`put_user_agent_config` or
        :meth:`delete_user_agent_config`.
        """
        # Check cache first
        cached = self._tool_cache.get(user_id)
        if cached is not None:
            tool_ids, ts = cached
            if (time.monotonic() - ts) < self._TOOL_CACHE_TTL:
                return list(tool_ids)  # return a copy

        # Cache miss or expired — recompute
        configs = self.get_user_agent_configs(user_id)
        tool_ids: list[str] = []

        for agent_cfg in sorted(configs, key=lambda c: c.agent_type):
            if not agent_cfg.enabled:
                continue

            template = self.get_template_by_type(agent_cfg.agent_type)
            if template is None:
                logger.warning(
                    "No template for agent type: %s (skipping)", agent_cfg.agent_type
                )
                continue

            if not self._is_available(template, user_id):
                logger.warning(
                    "User %s not authorized for agent %s (skipping)",
                    user_id,
                    agent_cfg.agent_type,
                )
                continue

            if agent_cfg.gateway_tool_id:
                tool_ids.append(agent_cfg.gateway_tool_id)

        # Store in cache
        self._tool_cache[user_id] = (list(tool_ids), time.monotonic())
        return tool_ids

    def invalidate_tool_cache(self, user_id: str) -> None:
        """Remove cached tool IDs for *user_id*.

        Called automatically when a user's agent config is created, updated,
        or deleted so that the next :meth:`build_sub_agent_tool_ids` call
        recomputes the tool set.
        """
        self._tool_cache.pop(user_id, None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_available(template: AgentTemplate, user_id: str) -> bool:
        avail = template.available_to
        if avail == "all":
            return True
        if isinstance(avail, list):
            return user_id in avail
        return False

    @staticmethod
    def _validate_available_to(available_to: str | list[str]) -> None:
        """Validate that *available_to* is ``"all"`` or a non-empty list of strings.

        Raises ``ValueError`` on invalid values.
        """
        if available_to == "all":
            return
        if isinstance(available_to, list):
            if len(available_to) == 0:
                raise ValueError(
                    "available_to must be 'all' or a non-empty list of user_ids"
                )
            for uid in available_to:
                if not isinstance(uid, str) or not uid.strip():
                    raise ValueError(
                        "Each entry in available_to must be a non-empty string"
                    )
            return
        raise ValueError(
            "available_to must be 'all' or a non-empty list of user_ids"
        )

    @staticmethod
    def _template_to_item(template: AgentTemplate) -> dict:
        """Convert an AgentTemplate dataclass to a DynamoDB item dict."""
        return {
            "template_id": template.template_id,
            "agent_type": template.agent_type,
            "name": template.name,
            "description": template.description,
            "system_prompt": template.system_prompt,
            "tool_server_ids": template.tool_server_ids,
            "default_config": template.default_config,
            "is_builtin": template.is_builtin,
            "available_to": template.available_to,
            "created_by": template.created_by,
            "created_at": template.created_at,
            "updated_at": template.updated_at,
        }

    @staticmethod
    def _item_to_template(item: dict) -> AgentTemplate:
        """Convert a DynamoDB item dict to an AgentTemplate dataclass."""
        return AgentTemplate(
            template_id=item["template_id"],
            agent_type=item["agent_type"],
            name=item["name"],
            description=item.get("description", ""),
            system_prompt=item.get("system_prompt", ""),
            tool_server_ids=item.get("tool_server_ids", []),
            default_config=item.get("default_config", {}),
            is_builtin=item.get("is_builtin", False),
            available_to=item.get("available_to", "all"),
            created_by=item.get("created_by", ""),
            created_at=item.get("created_at", ""),
            updated_at=item.get("updated_at", ""),
        )

    @staticmethod
    def _item_to_config(item: dict) -> AgentConfig:
        """Convert a DynamoDB item dict to an AgentConfig dataclass."""
        return AgentConfig(
            user_id=item["user_id"],
            agent_type=item["agent_type"],
            enabled=item.get("enabled", True),
            config=item.get("config", {}),
            gateway_tool_id=item.get("gateway_tool_id"),
            updated_at=item.get("updated_at", ""),
        )
