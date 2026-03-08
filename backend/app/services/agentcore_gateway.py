"""AgentCore Gateway Manager.

Replaces in-code tool definitions (health_tools.py, custom_agent.py tool
creation) with AgentCore Gateway-managed tool registrations and MCP server
configurations.  Manages tools at TWO levels:

1. **Orchestrator-level** — sub-agent routing tools (ask_health_advisor, …)
2. **Sub-agent-level** — domain-specific tools (health MCP, family MCP, …)

The two tool sets are kept strictly disjoint: orchestrator tools never
contain domain tools and vice-versa.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ToolDefinition
# ---------------------------------------------------------------------------


@dataclass
class ToolDefinition:
    """A single tool exposed via the Gateway."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    server_id: str | None = None
    version: str = "1"

    # Discriminator: "routing" for orchestrator-level, "domain" for sub-agent
    level: str = "domain"


# ---------------------------------------------------------------------------
# Internal registry types
# ---------------------------------------------------------------------------


@dataclass
class _McpServerRecord:
    """In-memory record for a registered MCP server."""

    server_id: str
    name: str
    endpoint: str
    auth_config: dict[str, Any] | None = None
    tools: list[ToolDefinition] = field(default_factory=list)
    healthy: bool = True


@dataclass
class _RoutingToolRecord:
    """In-memory record for an orchestrator-level routing tool."""

    tool_id: str
    agent_type: str
    description: str
    sub_agent_runtime_id: str



# ---------------------------------------------------------------------------
# Built-in health tools definition
# ---------------------------------------------------------------------------

HEALTH_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_family_health_records",
        "description": "Read health records for a family member",
        "parameters": {
            "target_user_id": {"type": "string", "required": True},
            "record_type": {"type": "string", "required": False},
        },
    },
    {
        "name": "get_health_summary",
        "description": "Get structured health summary grouped by record type",
        "parameters": {"target_user_id": {"type": "string", "required": True}},
    },
    {
        "name": "save_health_observation",
        "description": "Save a health observation from conversation",
        "parameters": {
            "target_user_id": {"type": "string", "required": True},
            "category": {"type": "string", "required": True},
            "summary": {"type": "string", "required": True},
            "detail": {"type": "string", "required": False},
            "confidence": {"type": "string", "required": False},
        },
    },
    {
        "name": "get_health_observations",
        "description": "Read past health observations and trends",
        "parameters": {
            "target_user_id": {"type": "string", "required": True},
            "category": {"type": "string", "required": False},
        },
    },
    {
        "name": "get_family_health_context",
        "description": "Get family composition, roles, and health notes",
        "parameters": {},
    },
    {
        "name": "search_health_conversations",
        "description": "Search past conversations for health topics",
        "parameters": {"keywords": {"type": "string", "required": True}},
    },
]


# ---------------------------------------------------------------------------
# AgentCoreGatewayManager
# ---------------------------------------------------------------------------


class AgentCoreGatewayManager:
    """Manages tool registrations at orchestrator and sub-agent levels.

    Uses in-memory data structures so the class is fully testable without
    real AWS services.  In production the methods would delegate to the
    AgentCore Gateway API.
    """

    def __init__(self, region: str) -> None:
        self._region = region

        # Orchestrator-level: routing tools keyed by agent_type
        self._routing_tools: dict[str, _RoutingToolRecord] = {}

        # Sub-agent-level: MCP / tool servers keyed by server_id
        self._tool_servers: dict[str, _McpServerRecord] = {}

        # Mapping: agent_type -> list of server_ids that provide its tools
        self._agent_tool_servers: dict[str, list[str]] = {}

        # Auto-increment counter for generating unique IDs
        self._next_id: int = 1

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _generate_id(self, prefix: str) -> str:
        sid = f"{prefix}-{self._next_id:04d}"
        self._next_id += 1
        return sid

    # ------------------------------------------------------------------
    # Orchestrator-Level Tool Management
    # ------------------------------------------------------------------

    def register_sub_agent_routing_tool(
        self,
        agent_type: str,
        description: str,
        sub_agent_runtime_id: str,
    ) -> str:
        """Register an orchestrator-level routing tool for a sub-agent.

        If a routing tool for *agent_type* already exists it is updated
        in-place and the existing tool_id is returned (idempotent).

        Returns the tool_id.
        """
        existing = self._routing_tools.get(agent_type)
        if existing is not None:
            existing.description = description
            existing.sub_agent_runtime_id = sub_agent_runtime_id
            return existing.tool_id

        tool_id = self._generate_id("rt")
        self._routing_tools[agent_type] = _RoutingToolRecord(
            tool_id=tool_id,
            agent_type=agent_type,
            description=description,
            sub_agent_runtime_id=sub_agent_runtime_id,
        )
        logger.info("Registered routing tool %s for %s", tool_id, agent_type)
        return tool_id

    def get_orchestrator_tools(
        self, enabled_agent_types: list[str]
    ) -> list[ToolDefinition]:
        """Return routing ToolDefinitions for the given agent types.

        Only returns tools whose agent_type is in *enabled_agent_types*.
        """
        tools: list[ToolDefinition] = []
        for agent_type in sorted(enabled_agent_types):
            rec = self._routing_tools.get(agent_type)
            if rec is None:
                continue
            tools.append(
                ToolDefinition(
                    name=f"ask_{agent_type}",
                    description=rec.description,
                    parameters={"query": {"type": "string", "required": True}},
                    server_id=rec.tool_id,
                    level="routing",
                )
            )
        return tools

    # ------------------------------------------------------------------
    # Sub-Agent-Level Tool Management
    # ------------------------------------------------------------------

    def register_mcp_server(
        self,
        name: str,
        endpoint: str,
        auth_config: dict | None = None,
    ) -> str:
        """Register an MCP server endpoint.

        Returns the server_id.
        """
        server_id = self._generate_id("mcp")
        self._tool_servers[server_id] = _McpServerRecord(
            server_id=server_id,
            name=name,
            endpoint=endpoint,
            auth_config=auth_config,
        )
        logger.info("Registered MCP server %s (%s)", server_id, name)
        return server_id

    def register_tool_server(
        self,
        server_name: str,
        server_type: str,
        endpoint: str,
        tools: list[ToolDefinition],
    ) -> str:
        """Register a tool server with an initial set of tools.

        *server_type* is ``"mcp"`` or ``"lambda"``.
        Returns the server_id.
        """
        server_id = self._generate_id("ts")
        for tool in tools:
            tool.server_id = server_id
            tool.level = "domain"
        self._tool_servers[server_id] = _McpServerRecord(
            server_id=server_id,
            name=server_name,
            endpoint=endpoint,
            tools=list(tools),
        )
        logger.info("Registered tool server %s (%s)", server_id, server_name)
        return server_id

    def update_tool_server(
        self, server_id: str, tools: list[ToolDefinition]
    ) -> None:
        """Replace the tool list for an existing server."""
        rec = self._tool_servers.get(server_id)
        if rec is None:
            raise ValueError(f"Unknown tool server: {server_id}")
        for tool in tools:
            tool.server_id = server_id
            tool.level = "domain"
        rec.tools = list(tools)

    def get_sub_agent_tools(self, agent_type: str) -> list[ToolDefinition]:
        """Return domain tools assigned to *agent_type*.

        Only returns tools from healthy servers.
        """
        server_ids = self._agent_tool_servers.get(agent_type, [])
        tools: list[ToolDefinition] = []
        for sid in server_ids:
            rec = self._tool_servers.get(sid)
            if rec is None or not rec.healthy:
                continue
            tools.extend(rec.tools)
        return tools

    # ------------------------------------------------------------------
    # Agent ↔ Server mapping
    # ------------------------------------------------------------------

    def assign_tool_servers_to_agent(
        self, agent_type: str, server_ids: list[str]
    ) -> None:
        """Associate tool servers with an agent type."""
        self._agent_tool_servers[agent_type] = list(server_ids)

    # ------------------------------------------------------------------
    # Tool Resolution
    # ------------------------------------------------------------------

    def resolve_tools_for_session(
        self, agent_type: str, user_id: str
    ) -> list[ToolDefinition]:
        """Resolve domain tools for a sub-agent session.

        Returns only the sub-agent-level tools for *agent_type*.
        """
        return self.get_sub_agent_tools(agent_type)

    # ------------------------------------------------------------------
    # Built-in agent tool registration (Task 9.3)
    # ------------------------------------------------------------------

    def register_builtin_tools(
        self,
        health_mcp_endpoint: str,
        family_mcp_endpoint: str,
    ) -> dict[str, str]:
        """Register MCP servers and tools for built-in agents.

        Registers:
        - Health tools MCP server with 6 health tools
        - Family tree tools MCP server
        - Assigns health tools to ``health_advisor`` agent type

        Returns mapping of logical name → server_id.
        """
        # Health MCP server
        health_server_id = self.register_mcp_server(
            name="homeagent-health-tools",
            endpoint=health_mcp_endpoint,
            auth_config={"type": "iam"},
        )
        health_tool_defs = [
            ToolDefinition(
                name=t["name"],
                description=t["description"],
                parameters=t["parameters"],
            )
            for t in HEALTH_TOOLS
        ]
        self.update_tool_server(health_server_id, health_tool_defs)

        # Family MCP server
        family_server_id = self.register_mcp_server(
            name="homeagent-family-tools",
            endpoint=family_mcp_endpoint,
            auth_config={"type": "iam"},
        )

        # Assign health tools to health_advisor
        self.assign_tool_servers_to_agent("health_advisor", [health_server_id])

        return {
            "health_tools": health_server_id,
            "family_tools": family_server_id,
        }

    def register_tools_for_template(
        self,
        agent_type: str,
        description: str,
        is_builtin: bool,
        tool_server_ids: list[str] | None = None,
    ) -> str:
        """Register a routing tool for a template and optionally assign servers.

        Called when a new template is created to ensure the orchestrator
        has a routing tool and the sub-agent has its domain tools.

        Returns the routing tool_id.
        """
        routing_tool_id = self.register_sub_agent_routing_tool(
            agent_type=agent_type,
            description=description,
            sub_agent_runtime_id=agent_type,
        )
        if tool_server_ids:
            self.assign_tool_servers_to_agent(agent_type, tool_server_ids)
        return routing_tool_id

    # ------------------------------------------------------------------
    # Built-in vs Custom agent handling (Task 9.4)
    # ------------------------------------------------------------------

    def get_agent_tool_config(
        self,
        agent_type: str,
        is_builtin: bool,
        system_prompt: str,
        tool_server_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return the tool configuration for a sub-agent session.

        Both built-in and custom agents follow the same path:
        1. Resolve routing tool at orchestrator level
        2. Resolve domain tools at sub-agent level

        The only difference: built-in agents get pre-registered MCP tools,
        custom agents rely on system_prompt with optional generic tools.
        """
        routing_rec = self._routing_tools.get(agent_type)
        routing_tool_id = routing_rec.tool_id if routing_rec else None

        domain_tools = self.get_sub_agent_tools(agent_type)

        return {
            "agent_type": agent_type,
            "is_builtin": is_builtin,
            "routing_tool_id": routing_tool_id,
            "system_prompt": system_prompt,
            "domain_tools": domain_tools,
            "tool_server_ids": tool_server_ids or [],
        }

    # ------------------------------------------------------------------
    # Error handling / health checks (Task 9.6)
    # ------------------------------------------------------------------

    def report_tool_error(
        self, server_id: str, error: str
    ) -> dict[str, Any]:
        """Report an MCP server error to the agent runtime.

        Returns an error payload that the agent LLM can use to inform
        the user about tool unavailability.
        """
        logger.error("Tool server %s error: %s", server_id, error)
        rec = self._tool_servers.get(server_id)
        server_name = rec.name if rec else server_id
        return {
            "error": True,
            "server_id": server_id,
            "server_name": server_name,
            "message": f"Tool server '{server_name}' encountered an error: {error}",
        }

    def run_health_check(self, server_id: str) -> bool:
        """Run a health check on a registered MCP server.

        In production this would ping the server endpoint.  The in-memory
        implementation simply returns the current healthy flag.

        Unhealthy servers are temporarily removed from tool resolution
        (get_sub_agent_tools skips them).
        """
        rec = self._tool_servers.get(server_id)
        if rec is None:
            return False
        return rec.healthy

    def mark_server_unhealthy(self, server_id: str) -> None:
        """Mark an MCP server as unhealthy so its tools are excluded."""
        rec = self._tool_servers.get(server_id)
        if rec is not None:
            rec.healthy = False
            logger.warning("Server %s marked unhealthy", server_id)

    def mark_server_healthy(self, server_id: str) -> None:
        """Restore an MCP server to healthy status."""
        rec = self._tool_servers.get(server_id)
        if rec is not None:
            rec.healthy = True
            logger.info("Server %s marked healthy", server_id)

    def run_all_health_checks(self) -> dict[str, bool]:
        """Return health status for all registered servers."""
        return {
            sid: rec.healthy for sid, rec in self._tool_servers.items()
        }

    # ------------------------------------------------------------------
    # Tool versioning (Task 9.8)
    # ------------------------------------------------------------------

    def update_tool_version(
        self,
        server_id: str,
        tool_name: str,
        new_version: str,
        updated_tool: ToolDefinition | None = None,
    ) -> None:
        """Update the version of a specific tool on a server.

        If *updated_tool* is provided, the tool definition is replaced.
        Otherwise only the version string is bumped.
        """
        rec = self._tool_servers.get(server_id)
        if rec is None:
            raise ValueError(f"Unknown tool server: {server_id}")

        for i, tool in enumerate(rec.tools):
            if tool.name == tool_name:
                if updated_tool is not None:
                    updated_tool.server_id = server_id
                    updated_tool.level = "domain"
                    updated_tool.version = new_version
                    rec.tools[i] = updated_tool
                else:
                    tool.version = new_version
                logger.info(
                    "Updated tool %s on server %s to version %s",
                    tool_name, server_id, new_version,
                )
                return

        raise ValueError(
            f"Tool '{tool_name}' not found on server {server_id}"
        )

    def get_tool_version(self, server_id: str, tool_name: str) -> str | None:
        """Return the current version string for a tool, or None."""
        rec = self._tool_servers.get(server_id)
        if rec is None:
            return None
        for tool in rec.tools:
            if tool.name == tool_name:
                return tool.version
        return None
