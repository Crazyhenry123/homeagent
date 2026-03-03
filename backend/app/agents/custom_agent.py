"""Generic custom agent factory — creates a Strands sub-agent from a template.

Used for admin-created agents that don't have a registered Python factory.
The template's system_prompt drives the agent's behavior.
"""

import logging

from strands import Agent, tool
from strands.models import BedrockModel

logger = logging.getLogger(__name__)


def create_custom_agent_tool(
    template: dict,
    config: dict,
    user_id: str,
    model_id: str,
) -> callable:
    """Create a @tool function from an agent template's system_prompt."""

    agent_type = template["agent_type"]
    tool_name = f"ask_{agent_type}"
    description = template.get("description", f"Ask the {template['name']} agent")
    system_prompt = template.get("system_prompt", "")

    @tool(name=tool_name, description=description)
    def ask_custom_agent(query: str) -> str:
        """Send a query to this custom agent.

        Args:
            query: The question or request for this agent.
        """
        model = BedrockModel(
            model_id=model_id,
            streaming=False,
            max_tokens=4096,
            temperature=0.5,
        )
        agent = Agent(model=model, system_prompt=system_prompt)
        try:
            result = agent(query)
            return str(result.message)
        except Exception:
            logger.exception("Custom agent %s failed", agent_type)
            return (
                f"I'm sorry, the {template['name']} agent wasn't able to "
                "process your request right now. Please try again."
            )

    return ask_custom_agent
