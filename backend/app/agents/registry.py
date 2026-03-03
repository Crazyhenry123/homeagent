"""Agent type registry — maps agent_type strings to factory functions.

Each factory returns a Strands @tool-decorated function that can be
attached to the personal agent as a sub-agent tool.
"""

import logging
from typing import Callable

logger = logging.getLogger(__name__)

# Registry of agent type -> factory function
_AGENT_FACTORIES: dict[str, Callable] = {}


def register_agent(agent_type: str) -> Callable:
    """Decorator to register an agent factory in the registry."""

    def wrapper(factory_fn: Callable) -> Callable:
        _AGENT_FACTORIES[agent_type] = factory_fn
        return factory_fn

    return wrapper


def get_agent_factory(agent_type: str) -> Callable | None:
    """Get the factory function for an agent type."""
    return _AGENT_FACTORIES.get(agent_type)


def get_registered_types() -> list[str]:
    """Return all registered agent type names."""
    return list(_AGENT_FACTORIES.keys())


def create_agent_tool(
    agent_type: str,
    config: dict,
    user_id: str,
    model_id: str,
) -> Callable | None:
    """Create a sub-agent tool for the given agent type.

    Returns a Strands @tool function or None if the type is not registered.
    """
    factory = get_agent_factory(agent_type)
    if factory is None:
        logger.warning("No factory registered for agent type: %s", agent_type)
        return None

    return factory(config=config, user_id=user_id, model_id=model_id)
