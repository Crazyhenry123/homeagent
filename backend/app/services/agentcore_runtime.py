"""AgentCore Runtime Client.

Replaces in-process Strands Agent instantiation with AgentCore Runtime
managed sessions.  The orchestrator agent and sub-agents are managed as
separate runtime agents, each backed by its own ECR container.

Key responsibilities:
- Map conversation_id ↔ session_id (bijective, no transformation)
- Create / reuse / delete orchestrator sessions
- Stream response events as StreamEvent objects
- Route orchestrator tool calls to sub-agent sessions
- Handle runtime errors with retry + fallback
- Handle sub-agent invocation errors gracefully

Uses in-memory backing stores so the class is fully testable without
real AWS services.  In production the methods would delegate to the
AgentCore Runtime API (InvokeAgentRuntime).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Generator

from app.models.agentcore import (
    CombinedSessionManager,
    MemoryConfig,
    StreamEvent,
    StreamEventType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AgentSession — represents a runtime session
# ---------------------------------------------------------------------------


@dataclass
class AgentSession:
    """An AgentCore Runtime session for an orchestrator or sub-agent."""

    session_id: str
    agent_id: str
    user_id: str = ""
    family_id: str = ""
    system_prompt: str = ""
    memory_config: MemoryConfig | None = None
    family_memory_config: MemoryConfig | None = None
    member_memory_config: MemoryConfig | None = None
    sub_agent_tool_ids: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    messages: list[dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# DeploymentConfig — describes how agents are deployed (Task 11.7)
# ---------------------------------------------------------------------------


@dataclass
class DeploymentConfig:
    """Describes the deployment model for an agent type.

    Each agent type (orchestrator + each sub-agent) is deployed as a
    separate AgentCore Runtime managed agent backed by its own ECR
    container.  All families are served from a single runtime instance
    per agent type; family-specific behaviour is resolved at invocation
    time.
    """

    agent_type: str
    agent_id: str
    ecr_image_uri: str = ""
    is_orchestrator: bool = False
    region: str = "us-east-1"


# ---------------------------------------------------------------------------
# Transient error detection
# ---------------------------------------------------------------------------

_TRANSIENT_ERROR_KEYWORDS = frozenset([
    "throttl",
    "timeout",
    "service unavailable",
    "internal server error",
    "connection",
    "temporarily",
])


def _is_transient_error(error: Exception) -> bool:
    """Heuristic: treat errors whose message contains transient keywords."""
    msg = str(error).lower()
    return any(kw in msg for kw in _TRANSIENT_ERROR_KEYWORDS)



# ---------------------------------------------------------------------------
# AgentCoreRuntimeClient
# ---------------------------------------------------------------------------


class AgentCoreRuntimeClient:
    """Manages orchestrator and sub-agent runtime sessions.

    Uses in-memory data structures so the class is fully testable without
    real AWS services.  In production the methods would delegate to the
    AgentCore Runtime API.
    """

    # Maximum retry attempts for transient errors
    MAX_RETRIES: int = 3
    # Base delay (seconds) for exponential backoff
    BASE_DELAY: float = 0.1

    def __init__(self, agent_id: str, region: str) -> None:
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        self._agent_id = agent_id
        self._region = region

        # In-memory session store: session_id -> AgentSession
        self._sessions: dict[str, AgentSession] = {}

        # Deployment registry: agent_type -> DeploymentConfig
        self._deployments: dict[str, DeploymentConfig] = {}

        # Sub-agent runtime clients: agent_type -> AgentCoreRuntimeClient
        self._sub_agent_clients: dict[str, AgentCoreRuntimeClient] = {}

        # Message persistence callback (set externally for DynamoDB writes)
        self._persist_message_callback: Any = None

        # Fallback model invocation callback (for persistent failures)
        self._fallback_invoke_callback: Any = None

        # Error injection hook for testing
        self._error_hook: Any = None

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def region(self) -> str:
        return self._region

    # ------------------------------------------------------------------
    # Session Management (Task 11.1)
    # ------------------------------------------------------------------

    def create_session(
        self,
        session_id: str,
        user_id: str,
        family_id: str,
        system_prompt: str,
        memory_config: MemoryConfig | CombinedSessionManager | None = None,
        sub_agent_tool_ids: list[str] | None = None,
    ) -> AgentSession:
        """Create a new orchestrator runtime session.

        The session_id MUST equal the conversation_id (bijective mapping,
        no transformation).  If a session with this ID already exists,
        a ValueError is raised — use get_session() to check first.

        Args:
            session_id: Must equal the conversation_id.
            user_id: Authenticated user.
            family_id: User's family group.
            system_prompt: Personalised orchestrator prompt.
            memory_config: Memory tier configuration (MemoryConfig or
                CombinedSessionManager).
            sub_agent_tool_ids: Gateway tool IDs for enabled sub-agents.

        Returns:
            The created AgentSession.

        Raises:
            ValueError: If session_id is empty or already exists.
        """
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if session_id in self._sessions:
            raise ValueError(f"Session already exists: {session_id}")

        family_mem = None
        member_mem = None
        single_mem = None

        if isinstance(memory_config, CombinedSessionManager):
            family_mem = memory_config.family_config
            member_mem = memory_config.member_config
        elif isinstance(memory_config, MemoryConfig):
            single_mem = memory_config

        session = AgentSession(
            session_id=session_id,
            agent_id=self._agent_id,
            user_id=user_id,
            family_id=family_id,
            system_prompt=system_prompt,
            memory_config=single_mem,
            family_memory_config=family_mem,
            member_memory_config=member_mem,
            sub_agent_tool_ids=list(sub_agent_tool_ids or []),
        )
        self._sessions[session_id] = session
        logger.info(
            "Created session %s for agent %s (user=%s, family=%s, tools=%d)",
            session_id,
            self._agent_id,
            user_id,
            family_id,
            len(session.sub_agent_tool_ids),
        )
        return session

    def get_session(self, session_id: str) -> AgentSession | None:
        """Return an existing session or None."""
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> None:
        """Delete a runtime session (called when conversation is deleted).

        No-op if the session does not exist.
        """
        removed = self._sessions.pop(session_id, None)
        if removed is not None:
            logger.info("Deleted session %s for agent %s", session_id, self._agent_id)
        else:
            logger.debug("Session %s not found for deletion", session_id)

    # ------------------------------------------------------------------
    # Streaming Response Handling (Task 11.3)
    # ------------------------------------------------------------------

    def invoke_session(
        self,
        session_id: str,
        message: str,
        stream: bool = True,
    ) -> Generator[StreamEvent, None, None]:
        """Invoke an orchestrator session and stream response events.

        Yields StreamEvent objects with type restricted to:
        text_delta, tool_use, message_done, error.

        On streaming complete with text content, persists the full
        assistant message (via callback) and emits message_done.

        Args:
            session_id: The session to invoke.
            message: The user's message.
            stream: Whether to stream (always True for SSE).

        Yields:
            StreamEvent objects.

        Raises:
            ValueError: If session does not exist.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        # Record user message
        session.messages.append({"role": "user", "content": message})

        # Check for injected errors (testing hook)
        if self._error_hook is not None:
            try:
                error = self._error_hook(session_id, message)
                if error is not None:
                    raise error
            except Exception as exc:
                # Attempt retry with backoff for transient errors
                yield from self._handle_invoke_error(
                    exc, session_id, message, session
                )
                return

        # In-memory simulation: generate a simple response
        response_text = f"Response to: {message}"
        full_text = ""

        # Emit text_delta events
        for chunk in self._simulate_streaming(response_text):
            full_text += chunk
            yield StreamEvent(
                type=StreamEventType.TEXT_DELTA.value,
                content=chunk,
            )

        # Persist and emit message_done
        if full_text:
            session.messages.append({"role": "assistant", "content": full_text})
            if self._persist_message_callback is not None:
                try:
                    self._persist_message_callback(session_id, "assistant", full_text)
                except Exception:
                    logger.warning(
                        "Failed to persist message for session %s",
                        session_id,
                        exc_info=True,
                    )

            yield StreamEvent(
                type=StreamEventType.MESSAGE_DONE.value,
                content=full_text,
                conversation_id=session_id,
            )

    def _simulate_streaming(self, text: str) -> list[str]:
        """Split text into chunks for simulated streaming."""
        words = text.split()
        if not words:
            return [text] if text else []
        chunks = []
        for i, word in enumerate(words):
            chunks.append(word + (" " if i < len(words) - 1 else ""))
        return chunks

    # ------------------------------------------------------------------
    # Runtime Error Handling (Task 11.8)
    # ------------------------------------------------------------------

    def _handle_invoke_error(
        self,
        error: Exception,
        session_id: str,
        message: str,
        session: AgentSession,
    ) -> Generator[StreamEvent, None, None]:
        """Handle runtime errors with retry + fallback + error event.

        1. Log error with session_id and agent_id
        2. Retry with exponential backoff for transient errors (up to 3)
        3. Fall back to direct model invocation for persistent failures
        4. Emit user-friendly error via SSE stream
        """
        logger.error(
            "Runtime error for session=%s agent=%s: %s",
            session_id,
            self._agent_id,
            error,
        )

        # Retry transient errors
        if _is_transient_error(error):
            for attempt in range(1, self.MAX_RETRIES + 1):
                delay = self.BASE_DELAY * (2 ** (attempt - 1))
                logger.info(
                    "Retry %d/%d for session %s (delay=%.2fs)",
                    attempt,
                    self.MAX_RETRIES,
                    session_id,
                    delay,
                )
                time.sleep(delay)

                try:
                    if self._error_hook is not None:
                        retry_error = self._error_hook(session_id, message)
                        if retry_error is not None:
                            raise retry_error
                    # Retry succeeded
                    response_text = f"Response to: {message}"
                    full_text = ""
                    for chunk in self._simulate_streaming(response_text):
                        full_text += chunk
                        yield StreamEvent(
                            type=StreamEventType.TEXT_DELTA.value,
                            content=chunk,
                        )
                    if full_text:
                        session.messages.append(
                            {"role": "assistant", "content": full_text}
                        )
                        yield StreamEvent(
                            type=StreamEventType.MESSAGE_DONE.value,
                            content=full_text,
                            conversation_id=session_id,
                        )
                    return
                except Exception as retry_err:
                    logger.warning(
                        "Retry %d failed for session %s: %s",
                        attempt,
                        session_id,
                        retry_err,
                    )
                    continue

        # Fallback to direct Bedrock model invocation
        if self._fallback_invoke_callback is not None:
            try:
                logger.info(
                    "Falling back to direct model invocation for session %s",
                    session_id,
                )
                fallback_text = self._fallback_invoke_callback(message)
                if fallback_text:
                    yield StreamEvent(
                        type=StreamEventType.TEXT_DELTA.value,
                        content=fallback_text,
                    )
                    yield StreamEvent(
                        type=StreamEventType.MESSAGE_DONE.value,
                        content=fallback_text,
                        conversation_id=session_id,
                    )
                    return
            except Exception as fb_err:
                logger.error("Fallback also failed: %s", fb_err)

        # Emit user-friendly error
        yield StreamEvent(
            type=StreamEventType.ERROR.value,
            content="AI service temporarily unavailable. Please try again.",
            data={"session_id": session_id, "agent_id": self._agent_id},
        )


    # ------------------------------------------------------------------
    # Orchestrator-to-Sub-Agent Routing (Task 11.5)
    # ------------------------------------------------------------------

    def register_sub_agent_client(
        self,
        agent_type: str,
        client: AgentCoreRuntimeClient,
    ) -> None:
        """Register a sub-agent runtime client for routing.

        The orchestrator uses these clients to create sub-agent sessions
        when a routing tool is invoked.
        """
        self._sub_agent_clients[agent_type] = client

    def invoke_sub_agent(
        self,
        agent_type: str,
        session_id: str,
        message: str,
        system_prompt: str,
        domain_tool_ids: list[str] | None = None,
    ) -> Generator[StreamEvent, None, None]:
        """Route a query to a sub-agent via InvokeAgentRuntime API.

        Creates a sub-agent session with:
        - The template-defined system_prompt
        - Only the sub-agent's own domain tools (no routing tools,
          no other sub-agents' tools)
        - The orchestrator's session_id for context passing

        The sub-agent response is returned to the orchestrator for
        inclusion in the user-facing stream.

        Args:
            agent_type: The sub-agent type (e.g. "health_advisor").
            session_id: The orchestrator's session_id (context passing).
            message: The query to route to the sub-agent.
            system_prompt: The sub-agent's template system_prompt.
            domain_tool_ids: The sub-agent's own domain tool IDs only.

        Yields:
            StreamEvent objects from the sub-agent.

        Raises:
            ValueError: If no client is registered for agent_type.
        """
        sub_client = self._sub_agent_clients.get(agent_type)
        if sub_client is None:
            raise ValueError(f"No sub-agent client registered for: {agent_type}")

        # Create or reuse sub-agent session
        sub_session_id = f"{session_id}__sub_{agent_type}"
        sub_session = sub_client.get_session(sub_session_id)

        if sub_session is None:
            try:
                sub_session = sub_client.create_session(
                    session_id=sub_session_id,
                    user_id="",  # Sub-agent doesn't need user context
                    family_id="",
                    system_prompt=system_prompt,
                    sub_agent_tool_ids=list(domain_tool_ids or []),
                )
            except Exception as exc:
                # Sub-agent session creation failed — handle gracefully
                yield from self._handle_sub_agent_error(agent_type, exc)
                return

        # Invoke sub-agent session
        try:
            yield from sub_client.invoke_session(
                session_id=sub_session_id,
                message=message,
            )
        except Exception as exc:
            yield from self._handle_sub_agent_error(agent_type, exc)

    # ------------------------------------------------------------------
    # Sub-Agent Invocation Error Handling (Task 11.10)
    # ------------------------------------------------------------------

    def _handle_sub_agent_error(
        self,
        agent_type: str,
        error: Exception,
    ) -> Generator[StreamEvent, None, None]:
        """Handle sub-agent errors gracefully.

        The orchestrator continues operating. The user is informed that
        the specific sub-agent is temporarily unavailable. Tool failures
        are reported (not silent).

        Args:
            agent_type: The sub-agent that failed.
            error: The error that occurred.

        Yields:
            A StreamEvent with type "error" describing the sub-agent failure.
        """
        logger.error(
            "Sub-agent '%s' error (agent_id=%s): %s",
            agent_type,
            self._agent_id,
            error,
        )

        # Report the error — not silent
        yield StreamEvent(
            type=StreamEventType.TEXT_DELTA.value,
            content=(
                f"I'm sorry, the {agent_type.replace('_', ' ')} is temporarily "
                f"unavailable. I'll try to help you directly instead."
            ),
            data={
                "sub_agent_error": True,
                "agent_type": agent_type,
                "error": str(error),
            },
        )

    # ------------------------------------------------------------------
    # Deployment Model Support (Task 11.7)
    # ------------------------------------------------------------------

    def register_deployment(self, config: DeploymentConfig) -> None:
        """Register a deployment configuration for an agent type.

        Each agent type is deployed as a separate AgentCore Runtime
        managed agent backed by its own ECR container.
        """
        self._deployments[config.agent_type] = config
        logger.info(
            "Registered deployment for %s (agent_id=%s, orchestrator=%s)",
            config.agent_type,
            config.agent_id,
            config.is_orchestrator,
        )

    def get_deployment(self, agent_type: str) -> DeploymentConfig | None:
        """Return the deployment config for an agent type, or None."""
        return self._deployments.get(agent_type)

    def list_deployments(self) -> list[DeploymentConfig]:
        """Return all registered deployment configurations."""
        return list(self._deployments.values())

    def resolve_family_context(
        self,
        agent_type: str,
        family_id: str,
        user_id: str,
    ) -> dict[str, str]:
        """Resolve family-specific behaviour at invocation time.

        All families are served from a single runtime instance per agent
        type.  This method returns the context needed to customise
        behaviour for a specific family/user.
        """
        return {
            "agent_type": agent_type,
            "family_id": family_id,
            "user_id": user_id,
        }

    # ------------------------------------------------------------------
    # Callback setters
    # ------------------------------------------------------------------

    def set_persist_message_callback(self, callback: Any) -> None:
        """Set the callback for persisting assistant messages to DynamoDB."""
        self._persist_message_callback = callback

    def set_fallback_invoke_callback(self, callback: Any) -> None:
        """Set the callback for direct Bedrock model invocation fallback."""
        self._fallback_invoke_callback = callback

    def set_error_hook(self, hook: Any) -> None:
        """Set an error injection hook for testing."""
        self._error_hook = hook
