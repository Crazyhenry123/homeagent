"""Personal agent factory — creates a per-user agent with enabled sub-agents.

The personal agent acts as a supervisor that routes to sub-agents based on
the user's query and enabled agent configurations.
"""

import logging
from typing import Callable

from app.agents.registry import create_agent_tool
from app.services.agent_config import get_agent_configs

logger = logging.getLogger(__name__)

# Ensure agent modules are imported so they register via @register_agent
import app.agents.health_advisor  # noqa: F401


def build_sub_agent_tools(
    user_id: str,
    model_id: str,
) -> list[Callable]:
    """Build the list of sub-agent tools for a user based on their agent configs.

    Looks up the user's enabled agent configurations and creates a
    @tool function for each one.
    """
    configs = get_agent_configs(user_id)
    tools = []

    for agent_cfg in configs:
        if not agent_cfg.get("enabled", False):
            continue

        agent_type = agent_cfg["agent_type"]
        config = agent_cfg.get("config", {})

        tool_fn = create_agent_tool(
            agent_type=agent_type,
            config=config,
            user_id=user_id,
            model_id=model_id,
        )
        if tool_fn is not None:
            tools.append(tool_fn)
            logger.info(
                "Enabled sub-agent %s for user %s", agent_type, user_id
            )

    return tools
