"""Property-based tests for AgentCoreGatewayManager.

Covers:
- Property 17: Gateway Two-Level Tool Isolation (Task 9.2)
- Property 4: Built-in vs Custom Agent Parity (Task 9.5)
- Property 16: Tool Parity (Task 9.7)

Uses Hypothesis for property-based testing where appropriate.
"""

from __future__ import annotations

import string

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.agentcore_gateway import (
    AgentCoreGatewayManager,
    HEALTH_TOOLS,
    ToolDefinition,
)

REGION = "us-east-1"

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_SLUG_FIRST = st.sampled_from(list(string.ascii_lowercase))
_SLUG_REST = st.text(
    alphabet=string.ascii_lowercase + string.digits + "_",
    min_size=1,
    max_size=15,
)
valid_agent_type = st.builds(lambda f, r: f + r, _SLUG_FIRST, _SLUG_REST)

non_empty_str = st.text(min_size=1, max_size=30).filter(lambda s: s.strip())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_gateway() -> AgentCoreGatewayManager:
    return AgentCoreGatewayManager(region=REGION)


def _register_routing_and_domain(
    gw: AgentCoreGatewayManager,
    agent_type: str,
    domain_tool_names: list[str] | None = None,
) -> tuple[str, str | None]:
    """Register a routing tool and optionally a domain tool server.

    Returns (routing_tool_id, server_id_or_None).
    """
    rt_id = gw.register_sub_agent_routing_tool(
        agent_type=agent_type,
        description=f"Route to {agent_type}",
        sub_agent_runtime_id=agent_type,
    )
    server_id = None
    if domain_tool_names:
        tools = [
            ToolDefinition(name=n, description=f"Tool {n}")
            for n in domain_tool_names
        ]
        server_id = gw.register_tool_server(
            server_name=f"{agent_type}-tools",
            server_type="mcp",
            endpoint=f"https://{agent_type}.example.com",
            tools=tools,
        )
        gw.assign_tool_servers_to_agent(agent_type, [server_id])
    return rt_id, server_id



# ===========================================================================
# Property 17: Gateway Two-Level Tool Isolation (Task 9.2)
# Validates: Requirements 9.1, 9.4, 9.5
# ===========================================================================


class TestGatewayTwoLevelToolIsolation:
    """**Validates: Requirements 9.1, 9.4, 9.5**

    Property 17: Gateway Two-Level Tool Isolation — orchestrator tool set
    contains only routing tools; sub-agent tool set contains only domain
    tools; no cross-level access.
    """

    @given(
        agent_type=valid_agent_type,
        domain_names=st.lists(
            st.text(
                alphabet=string.ascii_lowercase + "_",
                min_size=2,
                max_size=15,
            ).filter(lambda s: s.strip() and not s.startswith("ask_")),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=10, deadline=None)
    def test_orchestrator_tools_contain_only_routing_tools(
        self, agent_type: str, domain_names: list[str]
    ) -> None:
        """Orchestrator tool set contains only routing tools (ask_*)."""
        gw = _make_gateway()
        _register_routing_and_domain(gw, agent_type, domain_names)

        orch_tools = gw.get_orchestrator_tools([agent_type])

        for tool in orch_tools:
            assert tool.level == "routing", (
                f"Orchestrator tool '{tool.name}' has level '{tool.level}', "
                "expected 'routing'"
            )
            assert tool.name.startswith("ask_"), (
                f"Orchestrator tool '{tool.name}' does not start with 'ask_'"
            )

    @given(
        agent_type=valid_agent_type,
        domain_names=st.lists(
            st.text(
                alphabet=string.ascii_lowercase + "_",
                min_size=2,
                max_size=15,
            ).filter(lambda s: s.strip()),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=10, deadline=None)
    def test_sub_agent_tools_contain_only_domain_tools(
        self, agent_type: str, domain_names: list[str]
    ) -> None:
        """Sub-agent tool set contains only domain tools."""
        gw = _make_gateway()
        _register_routing_and_domain(gw, agent_type, domain_names)

        sub_tools = gw.get_sub_agent_tools(agent_type)

        for tool in sub_tools:
            assert tool.level == "domain", (
                f"Sub-agent tool '{tool.name}' has level '{tool.level}', "
                "expected 'domain'"
            )

    @given(
        agent_type=valid_agent_type,
        domain_names=st.lists(
            st.text(
                alphabet=string.ascii_lowercase + "_",
                min_size=2,
                max_size=15,
            ).filter(lambda s: s.strip()),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=10, deadline=None)
    def test_no_cross_level_access(
        self, agent_type: str, domain_names: list[str]
    ) -> None:
        """Orchestrator and sub-agent tool sets are disjoint."""
        gw = _make_gateway()
        _register_routing_and_domain(gw, agent_type, domain_names)

        orch_tools = gw.get_orchestrator_tools([agent_type])
        sub_tools = gw.get_sub_agent_tools(agent_type)

        orch_names = {t.name for t in orch_tools}
        sub_names = {t.name for t in sub_tools}

        overlap = orch_names & sub_names
        assert overlap == set(), (
            f"Cross-level overlap detected: {overlap}"
        )

    @given(
        types=st.lists(valid_agent_type, min_size=2, max_size=4, unique=True),
    )
    @settings(max_examples=5, deadline=None)
    def test_multiple_agents_maintain_isolation(
        self, types: list[str]
    ) -> None:
        """Each agent type's domain tools are isolated from others."""
        gw = _make_gateway()
        for i, at in enumerate(types):
            _register_routing_and_domain(
                gw, at, [f"tool_{at}_{j}" for j in range(2)]
            )

        for at in types:
            sub_tools = gw.get_sub_agent_tools(at)
            for tool in sub_tools:
                assert at in tool.name, (
                    f"Agent '{at}' received tool '{tool.name}' "
                    "which belongs to another agent"
                )

    def test_sub_agent_cannot_see_other_agents_tools(self) -> None:
        """A sub-agent cannot access another sub-agent's domain tools."""
        gw = _make_gateway()
        _register_routing_and_domain(gw, "health_advisor", ["get_records"])
        _register_routing_and_domain(gw, "shopping_assistant", ["search_products"])

        health_tools = gw.get_sub_agent_tools("health_advisor")
        shopping_tools = gw.get_sub_agent_tools("shopping_assistant")

        health_names = {t.name for t in health_tools}
        shopping_names = {t.name for t in shopping_tools}

        assert "search_products" not in health_names
        assert "get_records" not in shopping_names



# ===========================================================================
# Property 4: Built-in vs Custom Agent Parity (Task 9.5)
# Validates: Requirements 11.1, 11.3, 11.4
# ===========================================================================


class TestBuiltinVsCustomAgentParity:
    """**Validates: Requirements 11.1, 11.3, 11.4**

    Property 4: Built-in vs Custom Agent Parity — both built-in and custom
    agents follow same authorization/config/routing paths; only difference
    is MCP tool availability.
    """

    def _setup_builtin_and_custom(
        self, gw: AgentCoreGatewayManager
    ) -> tuple[str, str]:
        """Register a built-in and a custom agent, return their routing IDs."""
        # Built-in: health_advisor with MCP tools
        servers = gw.register_builtin_tools(
            health_mcp_endpoint="https://health.example.com",
            family_mcp_endpoint="https://family.example.com",
        )
        builtin_rt = gw.register_sub_agent_routing_tool(
            agent_type="health_advisor",
            description="Health advisor",
            sub_agent_runtime_id="health_advisor",
        )

        # Custom: my_custom_agent with no MCP tools
        custom_rt = gw.register_sub_agent_routing_tool(
            agent_type="my_custom_agent",
            description="Custom agent",
            sub_agent_runtime_id="my_custom_agent",
        )

        return builtin_rt, custom_rt

    def test_both_represented_as_routing_tools(self) -> None:
        """Both built-in and custom agents appear as routing tools."""
        gw = _make_gateway()
        self._setup_builtin_and_custom(gw)

        orch_tools = gw.get_orchestrator_tools(
            ["health_advisor", "my_custom_agent"]
        )
        names = {t.name for t in orch_tools}

        assert "ask_health_advisor" in names
        assert "ask_my_custom_agent" in names

    def test_both_follow_same_routing_path(self) -> None:
        """Both agent types go through get_agent_tool_config."""
        gw = _make_gateway()
        self._setup_builtin_and_custom(gw)

        builtin_cfg = gw.get_agent_tool_config(
            agent_type="health_advisor",
            is_builtin=True,
            system_prompt="You are a health advisor.",
        )
        custom_cfg = gw.get_agent_tool_config(
            agent_type="my_custom_agent",
            is_builtin=False,
            system_prompt="You are a custom agent.",
        )

        # Both have routing_tool_id
        assert builtin_cfg["routing_tool_id"] is not None
        assert custom_cfg["routing_tool_id"] is not None

        # Both have system_prompt
        assert builtin_cfg["system_prompt"] != ""
        assert custom_cfg["system_prompt"] != ""

    def test_builtin_has_domain_tools_custom_does_not(self) -> None:
        """Built-in agents get MCP tools; custom agents get none by default."""
        gw = _make_gateway()
        self._setup_builtin_and_custom(gw)

        builtin_cfg = gw.get_agent_tool_config(
            agent_type="health_advisor",
            is_builtin=True,
            system_prompt="",
        )
        custom_cfg = gw.get_agent_tool_config(
            agent_type="my_custom_agent",
            is_builtin=False,
            system_prompt="",
        )

        assert len(builtin_cfg["domain_tools"]) > 0, (
            "Built-in agent should have domain tools"
        )
        assert len(custom_cfg["domain_tools"]) == 0, (
            "Custom agent should have no domain tools by default"
        )

    @given(
        agent_type=valid_agent_type,
        is_builtin=st.booleans(),
        prompt=non_empty_str,
    )
    @settings(max_examples=10, deadline=None)
    def test_routing_tool_registered_regardless_of_builtin_flag(
        self, agent_type: str, is_builtin: bool, prompt: str
    ) -> None:
        """Both built-in and custom agents get a routing tool registered."""
        gw = _make_gateway()
        rt_id = gw.register_tools_for_template(
            agent_type=agent_type,
            description=f"Agent {agent_type}",
            is_builtin=is_builtin,
        )
        assert rt_id is not None

        orch_tools = gw.get_orchestrator_tools([agent_type])
        assert len(orch_tools) == 1
        assert orch_tools[0].name == f"ask_{agent_type}"
        assert orch_tools[0].level == "routing"

    def test_custom_agent_with_optional_tools(self) -> None:
        """Custom agents can optionally receive generic MCP tools."""
        gw = _make_gateway()

        # Register a generic tool server
        generic_sid = gw.register_mcp_server(
            name="generic-tools",
            endpoint="https://generic.example.com",
            auth_config={"type": "iam"},
        )
        gw.update_tool_server(
            generic_sid,
            [ToolDefinition(name="web_search", description="Search the web")],
        )

        # Register custom agent with the generic server
        gw.register_tools_for_template(
            agent_type="custom_searcher",
            description="Custom search agent",
            is_builtin=False,
            tool_server_ids=[generic_sid],
        )

        tools = gw.get_sub_agent_tools("custom_searcher")
        assert len(tools) == 1
        assert tools[0].name == "web_search"



# ===========================================================================
# Property 16: Tool Parity (Task 9.7)
# Validates: Requirements 26.1, 26.2
# ===========================================================================


class TestToolParity:
    """**Validates: Requirements 26.1, 26.2**

    Property 16: Tool Parity — for any tool in the current Strands Agent
    system, it is registered in Gateway and produces equivalent results
    via MCP.
    """

    def test_all_health_tools_registered_in_gateway(self) -> None:
        """All 6 health tools from the Strands system are registered."""
        gw = _make_gateway()
        gw.register_builtin_tools(
            health_mcp_endpoint="https://health.example.com",
            family_mcp_endpoint="https://family.example.com",
        )

        tools = gw.get_sub_agent_tools("health_advisor")
        registered_names = {t.name for t in tools}

        expected_names = {t["name"] for t in HEALTH_TOOLS}
        assert registered_names == expected_names, (
            f"Missing tools: {expected_names - registered_names}, "
            f"Extra tools: {registered_names - expected_names}"
        )

    def test_health_tool_definitions_match(self) -> None:
        """Each registered health tool has matching description and params."""
        gw = _make_gateway()
        gw.register_builtin_tools(
            health_mcp_endpoint="https://health.example.com",
            family_mcp_endpoint="https://family.example.com",
        )

        tools = gw.get_sub_agent_tools("health_advisor")
        tool_map = {t.name: t for t in tools}

        for expected in HEALTH_TOOLS:
            name = expected["name"]
            assert name in tool_map, f"Tool '{name}' not registered"
            registered = tool_map[name]
            assert registered.description == expected["description"], (
                f"Description mismatch for '{name}'"
            )
            assert registered.parameters == expected["parameters"], (
                f"Parameters mismatch for '{name}'"
            )

    def test_health_tools_count_is_six(self) -> None:
        """Exactly 6 health tools are registered."""
        gw = _make_gateway()
        gw.register_builtin_tools(
            health_mcp_endpoint="https://health.example.com",
            family_mcp_endpoint="https://family.example.com",
        )

        tools = gw.get_sub_agent_tools("health_advisor")
        assert len(tools) == 6

    def test_routing_tools_registered_for_templates(self) -> None:
        """Routing tools are registered for each agent template."""
        gw = _make_gateway()
        agent_types = ["health_advisor", "shopping_assistant", "logistics_assistant"]

        for at in agent_types:
            gw.register_sub_agent_routing_tool(
                agent_type=at,
                description=f"Route to {at}",
                sub_agent_runtime_id=at,
            )

        orch_tools = gw.get_orchestrator_tools(agent_types)
        orch_names = {t.name for t in orch_tools}

        for at in agent_types:
            assert f"ask_{at}" in orch_names, (
                f"Routing tool for '{at}' not found"
            )

    @given(
        tool_name=st.text(
            alphabet=string.ascii_lowercase + "_",
            min_size=3,
            max_size=20,
        ).filter(lambda s: s.strip()),
        description=non_empty_str,
    )
    @settings(max_examples=5, deadline=None)
    def test_registered_tool_retrievable_with_same_definition(
        self, tool_name: str, description: str
    ) -> None:
        """Any tool registered in Gateway is retrievable with same definition."""
        gw = _make_gateway()
        tool = ToolDefinition(
            name=tool_name,
            description=description,
            parameters={"input": {"type": "string"}},
        )
        sid = gw.register_tool_server(
            server_name="test-server",
            server_type="mcp",
            endpoint="https://test.example.com",
            tools=[tool],
        )
        gw.assign_tool_servers_to_agent("test_agent", [sid])

        retrieved = gw.get_sub_agent_tools("test_agent")
        assert len(retrieved) == 1
        assert retrieved[0].name == tool_name
        assert retrieved[0].description == description


# ===========================================================================
# Additional tests for error handling (Task 9.6) and versioning (Task 9.8)
# ===========================================================================


class TestGatewayErrorHandling:
    """Tests for gateway error handling — Task 9.6.

    **Validates: Requirements 23.1, 23.2, 23.3**
    """

    def test_report_tool_error_returns_error_payload(self) -> None:
        """report_tool_error returns structured error for LLM consumption."""
        gw = _make_gateway()
        sid = gw.register_mcp_server(
            name="health-tools",
            endpoint="https://health.example.com",
        )

        result = gw.report_tool_error(sid, "Connection timeout")
        assert result["error"] is True
        assert result["server_id"] == sid
        assert "Connection timeout" in result["message"]

    def test_unhealthy_server_excluded_from_tools(self) -> None:
        """Unhealthy servers are temporarily removed from tool resolution."""
        gw = _make_gateway()
        tools = [ToolDefinition(name="get_data", description="Get data")]
        sid = gw.register_tool_server(
            server_name="data-server",
            server_type="mcp",
            endpoint="https://data.example.com",
            tools=tools,
        )
        gw.assign_tool_servers_to_agent("data_agent", [sid])

        # Initially healthy
        assert len(gw.get_sub_agent_tools("data_agent")) == 1

        # Mark unhealthy
        gw.mark_server_unhealthy(sid)
        assert len(gw.get_sub_agent_tools("data_agent")) == 0

        # Restore
        gw.mark_server_healthy(sid)
        assert len(gw.get_sub_agent_tools("data_agent")) == 1

    def test_health_check_returns_status(self) -> None:
        """Health check returns current server status."""
        gw = _make_gateway()
        sid = gw.register_mcp_server(
            name="test-server",
            endpoint="https://test.example.com",
        )

        assert gw.run_health_check(sid) is True
        gw.mark_server_unhealthy(sid)
        assert gw.run_health_check(sid) is False

    def test_health_check_unknown_server(self) -> None:
        """Health check for unknown server returns False."""
        gw = _make_gateway()
        assert gw.run_health_check("nonexistent") is False

    def test_run_all_health_checks(self) -> None:
        """run_all_health_checks returns status for all servers."""
        gw = _make_gateway()
        s1 = gw.register_mcp_server("s1", "https://s1.example.com")
        s2 = gw.register_mcp_server("s2", "https://s2.example.com")
        gw.mark_server_unhealthy(s2)

        statuses = gw.run_all_health_checks()
        assert statuses[s1] is True
        assert statuses[s2] is False


class TestToolVersioning:
    """Tests for tool versioning — Task 9.8.

    **Validates: Requirements 26.3**
    """

    def test_update_tool_version(self) -> None:
        """Tool version can be updated via Gateway API."""
        gw = _make_gateway()
        tool = ToolDefinition(name="my_tool", description="A tool", version="1")
        sid = gw.register_tool_server(
            server_name="versioned-server",
            server_type="mcp",
            endpoint="https://v.example.com",
            tools=[tool],
        )

        assert gw.get_tool_version(sid, "my_tool") == "1"

        gw.update_tool_version(sid, "my_tool", "2")
        assert gw.get_tool_version(sid, "my_tool") == "2"

    def test_update_tool_version_with_new_definition(self) -> None:
        """Tool definition can be replaced during version update."""
        gw = _make_gateway()
        tool = ToolDefinition(
            name="my_tool", description="Old description", version="1"
        )
        sid = gw.register_tool_server(
            server_name="versioned-server",
            server_type="mcp",
            endpoint="https://v.example.com",
            tools=[tool],
        )

        new_tool = ToolDefinition(
            name="my_tool", description="New description"
        )
        gw.update_tool_version(sid, "my_tool", "2", updated_tool=new_tool)

        assert gw.get_tool_version(sid, "my_tool") == "2"
        gw.assign_tool_servers_to_agent("test_agent", [sid])
        tools = gw.get_sub_agent_tools("test_agent")
        assert tools[0].description == "New description"

    def test_update_nonexistent_tool_raises(self) -> None:
        """Updating a nonexistent tool raises ValueError."""
        gw = _make_gateway()
        sid = gw.register_mcp_server("s", "https://s.example.com")
        gw.update_tool_server(sid, [])

        with pytest.raises(ValueError, match="not found"):
            gw.update_tool_version(sid, "nonexistent", "2")

    def test_update_nonexistent_server_raises(self) -> None:
        """Updating a tool on nonexistent server raises ValueError."""
        gw = _make_gateway()
        with pytest.raises(ValueError, match="Unknown tool server"):
            gw.update_tool_version("bad-id", "tool", "2")

    def test_version_preserved_across_retrieval(self) -> None:
        """Version string is preserved when tools are retrieved."""
        gw = _make_gateway()
        tool = ToolDefinition(name="versioned", description="V", version="3")
        sid = gw.register_tool_server(
            server_name="vs",
            server_type="mcp",
            endpoint="https://vs.example.com",
            tools=[tool],
        )
        gw.assign_tool_servers_to_agent("vagent", [sid])

        retrieved = gw.get_sub_agent_tools("vagent")
        assert retrieved[0].version == "3"
