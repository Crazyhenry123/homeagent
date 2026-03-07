import logging
from typing import TYPE_CHECKING, Any

from flask import current_app

if TYPE_CHECKING:
    from bedrock_agentcore.memory.integrations.strands.session_manager import (
        AgentCoreMemorySessionManager,
    )

logger = logging.getLogger(__name__)


def retrieve_long_term_memories(user_id: str, query: str) -> str:
    """Retrieve long-term memories (preferences, facts) from AgentCore Memory.

    Returns a formatted string of relevant memories for prompt injection,
    or empty string if AgentCore is not configured or unavailable.
    """
    memory_id = current_app.config.get("AGENTCORE_MEMORY_ID")
    if not memory_id:
        return ""

    try:
        from bedrock_agentcore.memory import MemoryClient
    except ImportError:
        logger.debug("bedrock-agentcore not installed, skipping memory retrieval")
        return ""

    region = current_app.config["AWS_REGION"]

    try:
        client = MemoryClient(region_name=region)
        # Retrieve from preferences and facts namespaces
        results: list[dict[str, Any]] = []
        for namespace in [f"/preferences/{user_id}", f"/facts/{user_id}"]:
            try:
                resp = client.retrieve(
                    memory_id=memory_id,
                    namespace=namespace,
                    query=query,
                    top_k=5,
                )
                items = resp.get("results", [])
                results.extend(items)
            except Exception:
                logger.debug("Failed to retrieve from namespace %s", namespace)

        if not results:
            return ""

        # Format memories for prompt injection
        lines = ["\nRecalled memories about this user:"]
        for item in results:
            content = item.get("content", "")
            if content:
                lines.append(f"- {content}")

        return "\n".join(lines) if len(lines) > 1 else ""

    except Exception:
        logger.debug("AgentCore Memory retrieval failed", exc_info=True)
        return ""


def create_session_manager(
    user_id: str,
    conversation_id: str,
) -> "AgentCoreMemorySessionManager | None":
    """Create an AgentCore Memory session manager for a user.

    Uses the user_id as actor_id for per-user persistent memory, and
    conversation_id as session_id for per-conversation context.

    Returns None if AgentCore Memory is not configured (AGENTCORE_MEMORY_ID unset).
    """
    memory_id = current_app.config.get("AGENTCORE_MEMORY_ID")
    if not memory_id:
        return None

    try:
        from bedrock_agentcore.memory.integrations.strands.config import (
            AgentCoreMemoryConfig,
            RetrievalConfig,
        )
        from bedrock_agentcore.memory.integrations.strands.session_manager import (
            AgentCoreMemorySessionManager,
        )
    except ImportError:
        logger.warning(
            "bedrock-agentcore package not installed, AgentCore Memory disabled"
        )
        return None

    region = current_app.config["AWS_REGION"]

    config = AgentCoreMemoryConfig(
        memory_id=memory_id,
        session_id=conversation_id,
        actor_id=user_id,
        retrieval_config={
            "/preferences/{actorId}": RetrievalConfig(
                top_k=5,
                relevance_score=0.7,
            ),
            "/facts/{actorId}": RetrievalConfig(
                top_k=10,
                relevance_score=0.3,
            ),
            "/summaries/{actorId}/{sessionId}": RetrievalConfig(
                top_k=5,
                relevance_score=0.5,
            ),
        },
    )

    try:
        session_manager = AgentCoreMemorySessionManager(
            config, region_name=region
        )
        return session_manager
    except Exception:
        logger.exception("Failed to create AgentCore Memory session manager")
        return None
