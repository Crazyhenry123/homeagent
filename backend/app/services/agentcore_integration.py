"""AgentCore Integration Module.

Wires together AgentManagementClient, AgentCoreGatewayManager,
AgentCoreMemoryManager, and AgentCoreRuntimeClient to implement:
- Dynamic sub-agent addition/removal (add_sub_agent_for_user, remove_sub_agent_for_user)
- Migrated chat endpoint (stream_agent_chat_v2)
"""

from __future__ import annotations

import logging
from typing import Generator

from app.models.agentcore import AgentConfig, StreamEvent
from app.services.agent_management import AgentManagementClient
from app.services.agentcore_gateway import AgentCoreGatewayManager
from app.services.agentcore_memory import AgentCoreMemoryManager
from app.services.agentcore_runtime import AgentCoreRuntimeClient
from app.services.conversation import add_message

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dynamic Sub-Agent Addition / Removal
# ---------------------------------------------------------------------------


def add_sub_agent_for_user(
    agent_mgmt: AgentManagementClient,
    gateway: AgentCoreGatewayManager,
    user_id: str,
    agent_type: str,
    config: dict | None = None,
    requesting_user_id: str | None = None,
    requesting_user_role: str | None = None,
) -> AgentConfig:
    """Add a sub-agent for a user.

    Validates the template exists, checks authorization, enforces admin role
    for cross-user operations, merges config, registers the gateway routing
    tool, and creates the AgentConfig.

    The next orchestrator session for this user will include the new
    sub-agent's routing tool because ``build_sub_agent_tool_ids`` re-resolves
    on each session creation (with 60s cache that is invalidated on config
    change).

    Raises:
        ValueError: If agent_type is unknown or user is not authorized.
        PermissionError: If non-admin attempts cross-user modification.
    """
    # 1. Validate template exists
    template = agent_mgmt.get_template_by_type(agent_type)
    if template is None:
        raise ValueError(f"Unknown agent type: {agent_type}")

    # 2. Check authorization
    if not agent_mgmt.is_user_authorized_for_template(user_id, template):
        raise PermissionError(
            f"User {user_id} is not authorized for agent type {agent_type}"
        )

    # 3. Check admin role for cross-user modification
    if (
        requesting_user_id is not None
        and requesting_user_id != user_id
        and requesting_user_role != "admin"
    ):
        raise PermissionError("Only admins can configure agents for other users")

    # 4. Merge config with template defaults
    merged_config = {**template.default_config, **(config or {})}

    # 5. Register gateway routing tool (idempotent)
    gateway_tool_id = gateway.register_sub_agent_routing_tool(
        agent_type=agent_type,
        description=template.description,
        sub_agent_runtime_id=agent_type,
    )

    # 6. Create AgentConfig via the management client
    agent_config = agent_mgmt.put_user_agent_config(
        user_id=user_id,
        agent_type=agent_type,
        enabled=True,
        config=merged_config,
        requesting_user_id=requesting_user_id,
        requesting_user_role=requesting_user_role,
    )

    logger.info(
        "Added sub-agent %s for user %s (gateway_tool_id=%s)",
        agent_type,
        user_id,
        gateway_tool_id,
    )
    return agent_config


def remove_sub_agent_for_user(
    agent_mgmt: AgentManagementClient,
    user_id: str,
    agent_type: str,
    requesting_user_id: str | None = None,
    requesting_user_role: str | None = None,
) -> bool:
    """Remove a sub-agent for a user.

    Checks admin role for cross-user operations, then deletes the
    AgentConfig. Does NOT delete the gateway routing tool — other users
    may still reference it.

    The next orchestrator session for this user will exclude this
    sub-agent's routing tool.

    Returns True if the config existed and was deleted, False otherwise.

    Raises:
        PermissionError: If non-admin attempts cross-user modification.
    """
    # Check admin role for cross-user modification
    if (
        requesting_user_id is not None
        and requesting_user_id != user_id
        and requesting_user_role != "admin"
    ):
        raise PermissionError("Only admins can configure agents for other users")

    deleted = agent_mgmt.delete_user_agent_config(
        user_id=user_id,
        agent_type=agent_type,
        requesting_user_id=requesting_user_id,
        requesting_user_role=requesting_user_role,
    )

    if deleted:
        logger.info("Removed sub-agent %s for user %s", agent_type, user_id)
    else:
        logger.warning(
            "No config found for user %s agent_type %s", user_id, agent_type
        )

    # NOTE: Gateway routing tool is NOT deleted — other users may reference it
    return deleted


# ---------------------------------------------------------------------------
# Migrated Chat Endpoint (stream_agent_chat_v2)
# ---------------------------------------------------------------------------


def stream_agent_chat_v2(
    runtime_client: AgentCoreRuntimeClient,
    agent_mgmt: AgentManagementClient,
    memory_manager: AgentCoreMemoryManager,
    messages: list[dict],
    user_id: str,
    family_id: str | None,
    conversation_id: str,
    system_prompt: str | None = None,
) -> Generator[dict, None, None]:
    """Stream an agent chat response using AgentCore Runtime.

    Wires together:
    1. Resolve sub-agent tools via AgentManagementClient
    2. Build memory config via AgentCoreMemoryManager
    3. Create or resume session via AgentCoreRuntimeClient
    4. Invoke with streaming
    5. Persist assistant message on completion

    Yields dicts with keys: type, content, conversation_id.
    """
    # Step 1: Resolve user's authorized and enabled sub-agents
    sub_agent_tool_ids = agent_mgmt.build_sub_agent_tool_ids(user_id)

    # Step 2: Build memory configuration (dual-tier)
    memory_config = None
    if family_id:
        try:
            memory_config = memory_manager.create_combined_session_manager(
                family_id=family_id,
                member_id=user_id,
                session_id=conversation_id,
            )
        except Exception:
            logger.warning(
                "Failed to create combined session manager for user %s, "
                "proceeding without memory",
                user_id,
                exc_info=True,
            )

    # Step 3: Create or resume orchestrator session
    session = runtime_client.get_session(conversation_id)
    if session is None:
        personalized_prompt = system_prompt or (
            "You are a helpful family assistant. Be warm, friendly, and supportive."
        )
        session = runtime_client.create_session(
            session_id=conversation_id,
            user_id=user_id,
            family_id=family_id or "",
            system_prompt=personalized_prompt,
            memory_config=memory_config,
            sub_agent_tool_ids=sub_agent_tool_ids,
        )

    # Step 4: Invoke orchestrator with streaming
    user_message = messages[-1]["content"] if messages else ""
    full_text = ""

    for event in runtime_client.invoke_session(
        session_id=conversation_id,
        message=user_message,
        stream=True,
    ):
        if event.type == "text_delta":
            full_text += event.content
            yield {"type": "text_delta", "content": event.content}
        elif event.type == "tool_use":
            yield {"type": "tool_use", "content": event.content}
        elif event.type == "error":
            yield {"type": "error", "content": event.content}
            return

    # Step 5: Persist and finalize
    if full_text:
        add_message(conversation_id, "assistant", full_text)
        yield {
            "type": "message_done",
            "content": full_text,
            "conversation_id": conversation_id,
        }
