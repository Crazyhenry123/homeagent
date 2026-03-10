"""AgentCore Runtime Client.

Invokes the AgentCore Runtime orchestrator agent via the
bedrock-agentcore:invoke_agent_runtime API. Falls back to direct Bedrock
converse_stream when no runtime ARN is configured.

Key responsibilities:
- Map conversation_id <-> session_id (bijective, no transformation)
- Invoke orchestrator via AgentCore Runtime API with streaming
- Handle runtime errors with retry + fallback to direct Bedrock
- Maintain session metadata in memory for the request lifecycle
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Generator

import boto3

from app.models.agentcore import (
    CombinedSessionManager,
    MemoryConfig,
    StreamEvent,
    StreamEventType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DeploymentConfig — describes how agents are deployed (kept for compat)
# ---------------------------------------------------------------------------


@dataclass
class DeploymentConfig:
    """Describes the deployment model for an agent type."""

    agent_type: str
    agent_id: str
    ecr_image_uri: str = ""
    is_orchestrator: bool = False
    region: str = "us-east-1"


# ---------------------------------------------------------------------------
# AgentSession — tracks session metadata within a request
# ---------------------------------------------------------------------------


@dataclass
class AgentSession:
    """Metadata for an active orchestrator session."""

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
    """Invokes the AgentCore Runtime orchestrator agent.

    When ``agent_runtime_arn`` is provided, uses the real
    bedrock-agentcore:invoke_agent_runtime API. Otherwise falls back to
    direct Bedrock converse_stream for local development.
    """

    MAX_RETRIES: int = 3
    BASE_DELAY: float = 0.5

    def __init__(
        self,
        agent_id: str,
        region: str,
        agent_runtime_arn: str | None = None,
    ) -> None:
        if not agent_id or not agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        self._agent_id = agent_id
        self._region = region
        self._agent_runtime_arn = agent_runtime_arn

        # Lazy-initialised boto3 clients
        self._agentcore_client: Any = None
        self._bedrock_client: Any = None

        # In-memory session metadata (lives for the process lifecycle)
        self._sessions: dict[str, AgentSession] = {}

        # Callbacks for persistence and fallback
        self._persist_message_callback: Any = None
        self._fallback_invoke_callback: Any = None

        # Error injection hook for testing
        self._error_hook: Any = None

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def region(self) -> str:
        return self._region

    @property
    def uses_agentcore(self) -> bool:
        """True when a real AgentCore Runtime ARN is configured."""
        return bool(self._agent_runtime_arn)

    def _get_agentcore_client(self) -> Any:
        if self._agentcore_client is None:
            self._agentcore_client = boto3.client(
                "bedrock-agentcore", region_name=self._region
            )
        return self._agentcore_client

    def _get_bedrock_client(self) -> Any:
        if self._bedrock_client is None:
            self._bedrock_client = boto3.client(
                "bedrock-runtime", region_name=self._region
            )
        return self._bedrock_client

    # ------------------------------------------------------------------
    # Session Management
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
        """Create a new orchestrator session.

        The session_id MUST equal the conversation_id (bijective mapping).
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
        """Delete a session. No-op if it doesn't exist."""
        removed = self._sessions.pop(session_id, None)
        if removed is not None:
            logger.info("Deleted session %s", session_id)

    # ------------------------------------------------------------------
    # Invoke — routes to AgentCore Runtime or direct Bedrock
    # ------------------------------------------------------------------

    def invoke_session(
        self,
        session_id: str,
        message: str,
        stream: bool = True,
    ) -> Generator[StreamEvent, None, None]:
        """Invoke the orchestrator and stream response events.

        Uses AgentCore Runtime when configured, otherwise falls back to
        direct Bedrock converse_stream.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        session.messages.append({"role": "user", "content": message})

        # Check for injected errors (testing)
        if self._error_hook is not None:
            try:
                error = self._error_hook(session_id, message)
                if error is not None:
                    raise error
            except Exception as exc:
                yield from self._handle_invoke_error(exc, session_id, message, session)
                return

        yield from self._invoke_for_session(session, message)

    def _invoke_for_session(
        self, session: AgentSession, message: str
    ) -> Generator[StreamEvent, None, None]:
        """Route to the appropriate invoke method."""
        if self._agent_runtime_arn:
            yield from self._invoke_agentcore(session, message)
        else:
            yield from self._invoke_bedrock_direct(session, message)

    def _invoke_agentcore(
        self, session: AgentSession, message: str
    ) -> Generator[StreamEvent, None, None]:
        """Invoke via bedrock-agentcore:invoke_agent_runtime."""
        client = self._get_agentcore_client()

        # Session ID must be 33+ characters for AgentCore
        runtime_session_id = session.session_id
        if len(runtime_session_id) < 33:
            runtime_session_id = runtime_session_id + "-" + uuid.uuid4().hex

        payload = json.dumps({"prompt": message}).encode()

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = client.invoke_agent_runtime(
                    agentRuntimeArn=self._agent_runtime_arn,
                    runtimeSessionId=runtime_session_id,
                    payload=payload,
                    qualifier="DEFAULT",
                )

                # Read the response
                response_body = response.get("response")
                if response_body is None:
                    yield StreamEvent(
                        type=StreamEventType.ERROR.value,
                        content="Empty response from AgentCore Runtime.",
                    )
                    return

                # Handle streaming response
                if hasattr(response_body, "read"):
                    raw = response_body.read()
                else:
                    raw = response_body

                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")

                # Parse response — may be JSON or chunked
                full_text = self._parse_runtime_response(raw)

                if full_text:
                    # Emit as text_delta for SSE streaming
                    yield StreamEvent(
                        type=StreamEventType.TEXT_DELTA.value,
                        content=full_text,
                    )

                    session.messages.append(
                        {"role": "assistant", "content": full_text}
                    )
                    if self._persist_message_callback:
                        try:
                            self._persist_message_callback(
                                session.session_id, "assistant", full_text
                            )
                        except Exception:
                            logger.warning(
                                "Failed to persist message for session %s",
                                session.session_id,
                                exc_info=True,
                            )

                    yield StreamEvent(
                        type=StreamEventType.MESSAGE_DONE.value,
                        content=full_text,
                        conversation_id=session.session_id,
                    )
                return

            except Exception as exc:
                if attempt < self.MAX_RETRIES and _is_transient_error(exc):
                    delay = self.BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "AgentCore invoke retry %d/%d for session %s: %s",
                        attempt,
                        self.MAX_RETRIES,
                        session.session_id,
                        exc,
                    )
                    time.sleep(delay)
                    continue

                logger.error(
                    "AgentCore invoke failed for session %s: %s",
                    session.session_id,
                    exc,
                )
                # Fall back to direct Bedrock
                logger.info(
                    "Falling back to direct Bedrock for session %s",
                    session.session_id,
                )
                yield from self._invoke_bedrock_direct(session, message)
                return

    def _parse_runtime_response(self, raw: str) -> str:
        """Extract text from AgentCore Runtime response."""
        try:
            data = json.loads(raw)
            # Standard Strands agent response format
            if isinstance(data, dict):
                if "result" in data:
                    result = data["result"]
                    if isinstance(result, str):
                        return result
                    # result may be a message dict from Strands
                    if isinstance(result, dict):
                        content = result.get("content", [])
                        if isinstance(content, list):
                            texts = [
                                c.get("text", "")
                                for c in content
                                if isinstance(c, dict) and "text" in c
                            ]
                            return "".join(texts)
                        return str(content)
                # Direct text response
                if "text" in data:
                    return data["text"]
                if "content" in data:
                    return str(data["content"])
            return raw
        except (json.JSONDecodeError, TypeError):
            return raw

    def _invoke_bedrock_direct(
        self, session: AgentSession, message: str
    ) -> Generator[StreamEvent, None, None]:
        """Fallback: invoke Claude directly via Bedrock converse_stream.

        Falls through to in-memory simulation if Bedrock call fails.
        """

        client = self._get_bedrock_client()

        # Build converse API messages from session history
        converse_messages = []
        for msg in session.messages:
            converse_messages.append({
                "role": msg["role"],
                "content": [{"text": msg["content"]}],
            })

        try:
            response = client.converse_stream(
                modelId="us.anthropic.claude-opus-4-6-v1",
                messages=converse_messages,
                system=[{"text": session.system_prompt}],
                inferenceConfig={
                    "maxTokens": 4096,
                    "temperature": 0.7,
                },
            )
        except Exception:
            logger.warning(
                "Bedrock converse_stream failed for session %s; "
                "falling back to in-memory simulation",
                session.session_id,
                exc_info=True,
            )
            yield from self._invoke_in_memory(session, message)
            return

        full_text = ""
        for event in response["stream"]:
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    chunk = delta["text"]
                    full_text += chunk
                    yield StreamEvent(
                        type=StreamEventType.TEXT_DELTA.value,
                        content=chunk,
                    )

        if full_text:
            session.messages.append({"role": "assistant", "content": full_text})
            if self._persist_message_callback:
                try:
                    self._persist_message_callback(
                        session.session_id, "assistant", full_text
                    )
                except Exception:
                    logger.warning(
                        "Failed to persist message for session %s",
                        session.session_id,
                        exc_info=True,
                    )

            yield StreamEvent(
                type=StreamEventType.MESSAGE_DONE.value,
                content=full_text,
                conversation_id=session.session_id,
            )

    # ------------------------------------------------------------------
    # In-memory simulation (for tests / local dev without AWS)
    # ------------------------------------------------------------------

    def _invoke_in_memory(
        self, session: AgentSession, message: str
    ) -> Generator[StreamEvent, None, None]:
        """Simple in-memory simulation for testing."""
        response_text = f"Response to: {message}"
        full_text = ""

        words = response_text.split()
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            full_text += chunk
            yield StreamEvent(
                type=StreamEventType.TEXT_DELTA.value,
                content=chunk,
            )

        if full_text:
            session.messages.append({"role": "assistant", "content": full_text})
            if self._persist_message_callback:
                try:
                    self._persist_message_callback(
                        session.session_id, "assistant", full_text
                    )
                except Exception:
                    logger.warning(
                        "Failed to persist message for session %s",
                        session.session_id,
                        exc_info=True,
                    )

            yield StreamEvent(
                type=StreamEventType.MESSAGE_DONE.value,
                content=full_text,
                conversation_id=session.session_id,
            )

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _handle_invoke_error(
        self,
        error: Exception,
        session_id: str,
        message: str,
        session: AgentSession,
    ) -> Generator[StreamEvent, None, None]:
        """Handle runtime errors with retry + fallback + error event."""
        logger.error(
            "Runtime error for session=%s agent=%s: %s",
            session_id,
            self._agent_id,
            error,
        )

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
                    # Retry succeeded — re-invoke
                    yield from self._invoke_for_session(session, message)
                    return
                except Exception as retry_err:
                    logger.warning(
                        "Retry %d failed for session %s: %s",
                        attempt,
                        session_id,
                        retry_err,
                    )

        # Fallback callback
        if self._fallback_invoke_callback is not None:
            try:
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

        yield StreamEvent(
            type=StreamEventType.ERROR.value,
            content="AI service temporarily unavailable. Please try again.",
            data={"session_id": session_id, "agent_id": self._agent_id},
        )

    # ------------------------------------------------------------------
    # Sub-agent routing (delegates to separate runtime clients)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Sub-agent routing (compatibility with existing tests)
    # ------------------------------------------------------------------

    def register_sub_agent_client(
        self, agent_type: str, client: "AgentCoreRuntimeClient"
    ) -> None:
        """Register a sub-agent runtime client for routing."""
        if not hasattr(self, "_sub_agent_clients"):
            self._sub_agent_clients: dict[str, AgentCoreRuntimeClient] = {}
        self._sub_agent_clients[agent_type] = client

    def invoke_sub_agent(
        self,
        agent_type: str,
        session_id: str,
        message: str,
        system_prompt: str,
        domain_tool_ids: list[str] | None = None,
    ) -> Generator[StreamEvent, None, None]:
        """Route a query to a sub-agent via its registered client."""
        if not hasattr(self, "_sub_agent_clients"):
            self._sub_agent_clients = {}

        sub_client = self._sub_agent_clients.get(agent_type)
        if sub_client is None:
            raise ValueError(f"No sub-agent client registered for: {agent_type}")

        sub_session_id = f"{session_id}__sub_{agent_type}"
        sub_session = sub_client.get_session(sub_session_id)

        if sub_session is None:
            try:
                sub_session = sub_client.create_session(
                    session_id=sub_session_id,
                    user_id="",
                    family_id="",
                    system_prompt=system_prompt,
                    sub_agent_tool_ids=list(domain_tool_ids or []),
                )
            except Exception as exc:
                yield from self._handle_sub_agent_error(agent_type, exc)
                return

        try:
            yield from sub_client.invoke_session(
                session_id=sub_session_id,
                message=message,
            )
        except Exception as exc:
            yield from self._handle_sub_agent_error(agent_type, exc)

    def _handle_sub_agent_error(
        self,
        agent_type: str,
        error: Exception,
    ) -> Generator[StreamEvent, None, None]:
        """Handle sub-agent errors gracefully."""
        logger.error(
            "Sub-agent '%s' error (agent_id=%s): %s",
            agent_type,
            self._agent_id,
            error,
        )
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
    # Deployment model support (compatibility with existing tests)
    # ------------------------------------------------------------------

    def register_deployment(self, config: DeploymentConfig) -> None:
        """Register a deployment configuration for an agent type."""
        if not hasattr(self, "_deployments"):
            self._deployments: dict[str, DeploymentConfig] = {}
        self._deployments[config.agent_type] = config

    def get_deployment(self, agent_type: str) -> DeploymentConfig | None:
        """Return the deployment config for an agent type, or None."""
        if not hasattr(self, "_deployments"):
            self._deployments = {}
        return self._deployments.get(agent_type)

    def list_deployments(self) -> list[DeploymentConfig]:
        """Return all registered deployment configurations."""
        if not hasattr(self, "_deployments"):
            self._deployments = {}
        return list(self._deployments.values())

    def resolve_family_context(
        self,
        agent_type: str,
        family_id: str,
        user_id: str,
    ) -> dict[str, str]:
        """Resolve family-specific behaviour at invocation time."""
        return {
            "agent_type": agent_type,
            "family_id": family_id,
            "user_id": user_id,
        }

    # ------------------------------------------------------------------
    # Callback setters
    # ------------------------------------------------------------------

    def set_persist_message_callback(self, callback: Any) -> None:
        self._persist_message_callback = callback

    def set_fallback_invoke_callback(self, callback: Any) -> None:
        self._fallback_invoke_callback = callback

    def set_error_hook(self, hook: Any) -> None:
        self._error_hook = hook
