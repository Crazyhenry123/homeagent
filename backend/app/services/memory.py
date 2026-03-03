import logging

from flask import current_app

logger = logging.getLogger(__name__)


def create_session_manager(
    user_id: str,
    conversation_id: str,
) -> object | None:
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
