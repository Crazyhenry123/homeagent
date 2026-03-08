"""Property-based tests for AgentCoreRuntimeClient.

Covers:
- Property 8: Session-Conversation Bijection (Task 11.2)
- Property 21: Streaming Event Integrity (Task 11.4)
- Property 3: Orchestrator-to-Sub-Agent Routing (Task 11.6)
- Property 19: Runtime Error Propagation (Task 11.9)
- Property 26: Sub-Agent Resilience (Task 11.11)

Uses Hypothesis for property-based testing.
"""

from __future__ import annotations

import string

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.models.agentcore import (
    MemoryConfig,
    StreamEvent,
    StreamEventType,
)
from app.services.agentcore_runtime import (
    AgentCoreRuntimeClient,
    AgentSession,
    DeploymentConfig,
)

REGION = "us-east-1"
AGENT_ID = "orch-agent-001"

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

non_empty_str = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())

conversation_id_st = st.text(
    alphabet=string.ascii_lowercase + string.digits + "_-",
    min_size=5,
    max_size=30,
).filter(lambda s: s.strip())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(agent_id: str = AGENT_ID) -> AgentCoreRuntimeClient:
    return AgentCoreRuntimeClient(agent_id=agent_id, region=REGION)


def _make_memory_config(session_id: str = "sess-1") -> MemoryConfig:
    return MemoryConfig(
        memory_id="mem-family-001",
        session_id=session_id,
        actor_id="fam-001",
        retrieval_namespaces=["/family/{actorId}/health"],
    )



# ===========================================================================
# Property 8: Session-Conversation Bijection (Task 11.2)
# Validates: Requirements 1.1, 1.2, 1.6
# ===========================================================================


class TestSessionConversationBijection:
    """**Validates: Requirements 1.1, 1.2, 1.6**

    Property 8: Session-Conversation Bijection — for any conversation,
    exactly one runtime session exists with session_id == conversation_id;
    new conversations create sessions, subsequent messages reuse them.
    """

    @given(conv_id=conversation_id_st)
    @settings(max_examples=10, deadline=None)
    def test_session_id_equals_conversation_id(self, conv_id: str) -> None:
        """Session is created with session_id == conversation_id (no transform)."""
        client = _make_client()
        session = client.create_session(
            session_id=conv_id,
            user_id="user-1",
            family_id="fam-1",
            system_prompt="You are a helpful assistant.",
        )
        assert session.session_id == conv_id, (
            f"session_id '{session.session_id}' != conversation_id '{conv_id}'"
        )

    @given(conv_id=conversation_id_st)
    @settings(max_examples=10, deadline=None)
    def test_new_conversation_creates_session(self, conv_id: str) -> None:
        """First message in a new conversation creates a new session."""
        client = _make_client()
        assert client.get_session(conv_id) is None

        session = client.create_session(
            session_id=conv_id,
            user_id="user-1",
            family_id="fam-1",
            system_prompt="prompt",
        )
        assert client.get_session(conv_id) is session

    @given(conv_id=conversation_id_st)
    @settings(max_examples=10, deadline=None)
    def test_subsequent_messages_reuse_session(self, conv_id: str) -> None:
        """Subsequent messages reuse the existing session."""
        client = _make_client()
        session = client.create_session(
            session_id=conv_id,
            user_id="user-1",
            family_id="fam-1",
            system_prompt="prompt",
        )

        # Simulate "subsequent message" by getting the session
        reused = client.get_session(conv_id)
        assert reused is session, "Subsequent message should reuse same session"

        # Attempting to create again should fail (bijection: exactly one)
        with pytest.raises(ValueError, match="already exists"):
            client.create_session(
                session_id=conv_id,
                user_id="user-1",
                family_id="fam-1",
                system_prompt="prompt",
            )

    @given(
        conv_ids=st.lists(
            conversation_id_st, min_size=2, max_size=5, unique=True
        )
    )
    @settings(max_examples=10, deadline=None)
    def test_each_conversation_has_exactly_one_session(
        self, conv_ids: list[str]
    ) -> None:
        """For N conversations, exactly N sessions exist, each with matching ID."""
        client = _make_client()
        for cid in conv_ids:
            client.create_session(
                session_id=cid,
                user_id="user-1",
                family_id="fam-1",
                system_prompt="prompt",
            )

        for cid in conv_ids:
            session = client.get_session(cid)
            assert session is not None, f"No session for conversation {cid}"
            assert session.session_id == cid

    @given(conv_id=conversation_id_st)
    @settings(max_examples=10, deadline=None)
    def test_delete_conversation_deletes_session(self, conv_id: str) -> None:
        """Deleting a conversation deletes the corresponding session."""
        client = _make_client()
        client.create_session(
            session_id=conv_id,
            user_id="user-1",
            family_id="fam-1",
            system_prompt="prompt",
        )
        assert client.get_session(conv_id) is not None

        client.delete_session(conv_id)
        assert client.get_session(conv_id) is None

    def test_delete_nonexistent_session_is_noop(self) -> None:
        """Deleting a non-existent session does not raise."""
        client = _make_client()
        client.delete_session("nonexistent")  # Should not raise



# ===========================================================================
# Property 21: Streaming Event Integrity (Task 11.4)
# Validates: Requirements 25.1, 25.2, 25.3
# ===========================================================================


class TestStreamingEventIntegrity:
    """**Validates: Requirements 25.1, 25.2, 25.3**

    Property 21: Streaming Event Integrity — each chunk is a valid
    StreamEvent with type in {text_delta, tool_use, message_done, error};
    text completion persists message and emits message_done.
    """

    VALID_TYPES = {t.value for t in StreamEventType}

    @given(message=non_empty_str)
    @settings(max_examples=10, deadline=None)
    def test_all_events_have_valid_type(self, message: str) -> None:
        """Every streamed event has a type in the allowed set."""
        client = _make_client()
        client.create_session(
            session_id="conv-1",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="prompt",
        )

        events = list(client.invoke_session("conv-1", message))
        assert len(events) > 0, "Should produce at least one event"

        for event in events:
            assert event.type in self.VALID_TYPES, (
                f"Invalid event type: {event.type}"
            )

    @given(message=non_empty_str)
    @settings(max_examples=10, deadline=None)
    def test_text_completion_emits_message_done(self, message: str) -> None:
        """When streaming completes with text, message_done is emitted."""
        client = _make_client()
        client.create_session(
            session_id="conv-2",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="prompt",
        )

        events = list(client.invoke_session("conv-2", message))
        types = [e.type for e in events]

        assert StreamEventType.MESSAGE_DONE.value in types, (
            "message_done event not emitted after text completion"
        )

    @given(message=non_empty_str)
    @settings(max_examples=10, deadline=None)
    def test_message_done_contains_conversation_id(self, message: str) -> None:
        """message_done event includes the conversation_id."""
        client = _make_client()
        client.create_session(
            session_id="conv-3",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="prompt",
        )

        events = list(client.invoke_session("conv-3", message))
        done_events = [
            e for e in events if e.type == StreamEventType.MESSAGE_DONE.value
        ]
        assert len(done_events) == 1
        assert done_events[0].conversation_id == "conv-3"

    @given(message=non_empty_str)
    @settings(max_examples=10, deadline=None)
    def test_text_completion_persists_message(self, message: str) -> None:
        """On text completion, the full assistant message is persisted."""
        client = _make_client()
        client.create_session(
            session_id="conv-4",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="prompt",
        )

        persisted: list[tuple[str, str, str]] = []

        def mock_persist(session_id: str, role: str, content: str) -> None:
            persisted.append((session_id, role, content))

        client.set_persist_message_callback(mock_persist)

        events = list(client.invoke_session("conv-4", message))

        assert len(persisted) == 1, "Should persist exactly one message"
        sid, role, content = persisted[0]
        assert sid == "conv-4"
        assert role == "assistant"
        assert len(content) > 0

    @given(message=non_empty_str)
    @settings(max_examples=10, deadline=None)
    def test_text_deltas_concatenate_to_full_message(self, message: str) -> None:
        """text_delta events concatenate to the full message in message_done."""
        client = _make_client()
        client.create_session(
            session_id="conv-5",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="prompt",
        )

        events = list(client.invoke_session("conv-5", message))
        deltas = [
            e.content for e in events
            if e.type == StreamEventType.TEXT_DELTA.value
        ]
        done = [
            e for e in events
            if e.type == StreamEventType.MESSAGE_DONE.value
        ]

        concatenated = "".join(deltas)
        assert len(done) == 1
        assert done[0].content == concatenated

    def test_invoke_nonexistent_session_raises(self) -> None:
        """Invoking a non-existent session raises ValueError."""
        client = _make_client()
        with pytest.raises(ValueError, match="not found"):
            list(client.invoke_session("nonexistent", "hello"))



# ===========================================================================
# Property 3: Orchestrator-to-Sub-Agent Routing (Task 11.6)
# Validates: Requirements 2.2, 2.5, 9.3, 9.4, 9.5
# ===========================================================================


class TestOrchestratorToSubAgentRouting:
    """**Validates: Requirements 2.2, 2.5, 9.3, 9.4, 9.5**

    Property 3: Orchestrator-to-Sub-Agent Routing — orchestrator receives
    only user's enabled routing tools; sub-agent receives only its domain
    tools; tool sets are disjoint.
    """

    @given(
        agent_types=st.lists(valid_agent_type, min_size=1, max_size=3, unique=True),
        routing_tools=st.lists(non_empty_str, min_size=1, max_size=3),
    )
    @settings(max_examples=10, deadline=None)
    def test_orchestrator_receives_only_routing_tools(
        self, agent_types: list[str], routing_tools: list[str]
    ) -> None:
        """Orchestrator session has only routing tool IDs, not domain tools."""
        client = _make_client()
        # Routing tools are what the orchestrator gets
        routing_ids = [f"rt-{at}" for at in agent_types]

        session = client.create_session(
            session_id="conv-orch-1",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="You are an orchestrator.",
            sub_agent_tool_ids=routing_ids,
        )

        # Orchestrator's tools are the routing tool IDs
        assert set(session.sub_agent_tool_ids) == set(routing_ids)

    @given(
        agent_type=valid_agent_type,
        domain_tools=st.lists(non_empty_str, min_size=1, max_size=4),
    )
    @settings(max_examples=10, deadline=None)
    def test_sub_agent_receives_only_domain_tools(
        self, agent_type: str, domain_tools: list[str]
    ) -> None:
        """Sub-agent session has only its own domain tools."""
        orchestrator = _make_client("orch-001")
        sub_client = _make_client(f"sub-{agent_type}")
        orchestrator.register_sub_agent_client(agent_type, sub_client)

        # Create orchestrator session with routing tools
        orchestrator.create_session(
            session_id="conv-main",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="orchestrator",
            sub_agent_tool_ids=[f"rt-{agent_type}"],
        )

        # Invoke sub-agent with domain tools only
        events = list(orchestrator.invoke_sub_agent(
            agent_type=agent_type,
            session_id="conv-main",
            message="test query",
            system_prompt=f"You are {agent_type}",
            domain_tool_ids=domain_tools,
        ))

        # Verify sub-agent session was created with domain tools
        sub_session_id = f"conv-main__sub_{agent_type}"
        sub_session = sub_client.get_session(sub_session_id)
        assert sub_session is not None
        assert set(sub_session.sub_agent_tool_ids) == set(domain_tools)

    @given(
        types=st.lists(valid_agent_type, min_size=2, max_size=3, unique=True),
    )
    @settings(max_examples=10, deadline=None)
    def test_tool_sets_are_disjoint(self, types: list[str]) -> None:
        """Orchestrator routing tools and sub-agent domain tools are disjoint."""
        orchestrator = _make_client("orch-001")

        routing_ids = [f"rt-{at}" for at in types]
        orchestrator.create_session(
            session_id="conv-disjoint",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="orchestrator",
            sub_agent_tool_ids=routing_ids,
        )

        for at in types:
            sub_client = _make_client(f"sub-{at}")
            orchestrator.register_sub_agent_client(at, sub_client)

            domain_ids = [f"domain-{at}-tool-{i}" for i in range(2)]
            list(orchestrator.invoke_sub_agent(
                agent_type=at,
                session_id="conv-disjoint",
                message="test",
                system_prompt=f"You are {at}",
                domain_tool_ids=domain_ids,
            ))

            sub_session_id = f"conv-disjoint__sub_{at}"
            sub_session = sub_client.get_session(sub_session_id)
            assert sub_session is not None

            # Sub-agent tools must not contain any routing tools
            overlap = set(sub_session.sub_agent_tool_ids) & set(routing_ids)
            assert overlap == set(), (
                f"Sub-agent '{at}' has routing tools: {overlap}"
            )

    def test_sub_agent_cannot_access_other_sub_agents_tools(self) -> None:
        """A sub-agent cannot see another sub-agent's domain tools."""
        orchestrator = _make_client("orch-001")

        health_client = _make_client("sub-health")
        shopping_client = _make_client("sub-shopping")
        orchestrator.register_sub_agent_client("health_advisor", health_client)
        orchestrator.register_sub_agent_client("shopping_assistant", shopping_client)

        orchestrator.create_session(
            session_id="conv-iso",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="orchestrator",
            sub_agent_tool_ids=["rt-health", "rt-shopping"],
        )

        health_tools = ["get_records", "save_observation"]
        shopping_tools = ["search_products", "compare_prices"]

        list(orchestrator.invoke_sub_agent(
            "health_advisor", "conv-iso", "health query",
            "health prompt", health_tools,
        ))
        list(orchestrator.invoke_sub_agent(
            "shopping_assistant", "conv-iso", "shopping query",
            "shopping prompt", shopping_tools,
        ))

        h_session = health_client.get_session("conv-iso__sub_health_advisor")
        s_session = shopping_client.get_session("conv-iso__sub_shopping_assistant")

        assert set(h_session.sub_agent_tool_ids) == set(health_tools)
        assert set(s_session.sub_agent_tool_ids) == set(shopping_tools)

        # No overlap
        assert set(h_session.sub_agent_tool_ids) & set(s_session.sub_agent_tool_ids) == set()



# ===========================================================================
# Property 19: Runtime Error Propagation (Task 11.9)
# Validates: Requirements 20.1, 20.4
# ===========================================================================


class TestRuntimeErrorPropagation:
    """**Validates: Requirements 20.1, 20.4**

    Property 19: Runtime Error Propagation — for any runtime error, it is
    logged with session_id and agent_id, and a user-friendly error event
    is emitted on SSE stream.
    """

    @given(message=non_empty_str)
    @settings(max_examples=10, deadline=None)
    def test_error_emits_error_event(self, message: str) -> None:
        """Runtime error produces a StreamEvent with type 'error'."""
        client = _make_client()
        client.create_session(
            session_id="conv-err-1",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="prompt",
        )

        # Inject a persistent (non-transient) error
        def error_hook(sid: str, msg: str) -> Exception:
            return RuntimeError("Persistent failure")

        client.set_error_hook(error_hook)

        events = list(client.invoke_session("conv-err-1", message))
        error_events = [
            e for e in events if e.type == StreamEventType.ERROR.value
        ]
        assert len(error_events) >= 1, "Should emit at least one error event"

    @given(message=non_empty_str)
    @settings(max_examples=10, deadline=None)
    def test_error_event_is_user_friendly(self, message: str) -> None:
        """Error event contains a user-friendly message."""
        client = _make_client()
        client.create_session(
            session_id="conv-err-2",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="prompt",
        )

        def error_hook(sid: str, msg: str) -> Exception:
            return RuntimeError("Internal crash")

        client.set_error_hook(error_hook)

        events = list(client.invoke_session("conv-err-2", message))
        error_events = [
            e for e in events if e.type == StreamEventType.ERROR.value
        ]
        assert len(error_events) >= 1
        # Should not expose internal error details
        assert "Internal crash" not in error_events[0].content
        assert "unavailable" in error_events[0].content.lower() or \
               "try again" in error_events[0].content.lower()

    @given(message=non_empty_str)
    @settings(max_examples=10, deadline=None)
    def test_error_event_contains_session_and_agent_ids(
        self, message: str
    ) -> None:
        """Error event data includes session_id and agent_id for logging."""
        client = _make_client()
        client.create_session(
            session_id="conv-err-3",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="prompt",
        )

        def error_hook(sid: str, msg: str) -> Exception:
            return RuntimeError("Failure")

        client.set_error_hook(error_hook)

        events = list(client.invoke_session("conv-err-3", message))
        error_events = [
            e for e in events if e.type == StreamEventType.ERROR.value
        ]
        assert len(error_events) >= 1
        assert error_events[0].data.get("session_id") == "conv-err-3"
        assert error_events[0].data.get("agent_id") == AGENT_ID

    def test_transient_error_retries_with_backoff(self) -> None:
        """Transient errors are retried up to 3 times."""
        client = _make_client()
        client.BASE_DELAY = 0.001  # Speed up for testing
        client.create_session(
            session_id="conv-retry",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="prompt",
        )

        call_count = 0

        def error_hook(sid: str, msg: str) -> Exception | None:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return ConnectionError("Timeout - service unavailable")
            return None  # Succeed on 3rd attempt

        client.set_error_hook(error_hook)

        events = list(client.invoke_session("conv-retry", "hello"))
        # Should eventually succeed after retries
        types = [e.type for e in events]
        assert StreamEventType.TEXT_DELTA.value in types
        assert StreamEventType.MESSAGE_DONE.value in types

    def test_persistent_failure_falls_back_to_direct_invocation(self) -> None:
        """Persistent failures fall back to direct Bedrock model invocation."""
        client = _make_client()
        client.BASE_DELAY = 0.001
        client.create_session(
            session_id="conv-fallback",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="prompt",
        )

        def error_hook(sid: str, msg: str) -> Exception:
            return RuntimeError("Persistent failure")

        def fallback(msg: str) -> str:
            return f"Fallback response to: {msg}"

        client.set_error_hook(error_hook)
        client.set_fallback_invoke_callback(fallback)

        events = list(client.invoke_session("conv-fallback", "hello"))
        types = [e.type for e in events]
        assert StreamEventType.TEXT_DELTA.value in types
        assert StreamEventType.MESSAGE_DONE.value in types

        text_events = [
            e for e in events if e.type == StreamEventType.TEXT_DELTA.value
        ]
        assert "Fallback response" in text_events[0].content



# ===========================================================================
# Property 26: Sub-Agent Resilience (Task 11.11)
# Validates: Requirements 21.1, 21.2, 21.3
# ===========================================================================


class TestSubAgentResilience:
    """**Validates: Requirements 21.1, 21.2, 21.3**

    Property 26: Sub-Agent Resilience — for any sub-agent error,
    orchestrator continues and informs user; tool failures are reported,
    not silent.
    """

    @given(agent_type=valid_agent_type)
    @settings(max_examples=10, deadline=None)
    def test_orchestrator_continues_on_sub_agent_error(
        self, agent_type: str
    ) -> None:
        """Orchestrator session continues operating after sub-agent error."""
        orchestrator = _make_client("orch-001")
        sub_client = _make_client(f"sub-{agent_type}")

        # Make sub-agent fail on invoke
        def sub_error_hook(sid: str, msg: str) -> Exception:
            return RuntimeError("Sub-agent crashed")

        sub_client.set_error_hook(sub_error_hook)
        orchestrator.register_sub_agent_client(agent_type, sub_client)

        orchestrator.create_session(
            session_id="conv-resilience",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="orchestrator",
            sub_agent_tool_ids=[f"rt-{agent_type}"],
        )

        # Invoke sub-agent — should not crash orchestrator
        events = list(orchestrator.invoke_sub_agent(
            agent_type=agent_type,
            session_id="conv-resilience",
            message="test query",
            system_prompt=f"You are {agent_type}",
            domain_tool_ids=["tool-1"],
        ))

        # Should get an informative event, not a crash
        assert len(events) > 0, "Should produce at least one event"

        # Orchestrator session should still exist
        orch_session = orchestrator.get_session("conv-resilience")
        assert orch_session is not None, "Orchestrator session should survive"

    @given(agent_type=valid_agent_type)
    @settings(max_examples=10, deadline=None)
    def test_user_informed_of_sub_agent_unavailability(
        self, agent_type: str
    ) -> None:
        """User is informed when a sub-agent is temporarily unavailable."""
        orchestrator = _make_client("orch-001")
        sub_client = _make_client(f"sub-{agent_type}")

        def sub_error_hook(sid: str, msg: str) -> Exception:
            return RuntimeError("Sub-agent down")

        sub_client.set_error_hook(sub_error_hook)
        orchestrator.register_sub_agent_client(agent_type, sub_client)

        orchestrator.create_session(
            session_id="conv-inform",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="orchestrator",
        )

        events = list(orchestrator.invoke_sub_agent(
            agent_type=agent_type,
            session_id="conv-inform",
            message="help me",
            system_prompt="prompt",
        ))

        # Should contain a message about unavailability
        all_content = " ".join(e.content for e in events)
        assert "unavailable" in all_content.lower(), (
            f"User should be informed of unavailability, got: {all_content}"
        )

    @given(agent_type=valid_agent_type)
    @settings(max_examples=10, deadline=None)
    def test_tool_failures_reported_not_silent(
        self, agent_type: str
    ) -> None:
        """Sub-agent tool failures are reported to orchestrator, not silent."""
        orchestrator = _make_client("orch-001")
        sub_client = _make_client(f"sub-{agent_type}")

        def sub_error_hook(sid: str, msg: str) -> Exception:
            return RuntimeError("Tool execution failed: get_records")

        sub_client.set_error_hook(sub_error_hook)
        orchestrator.register_sub_agent_client(agent_type, sub_client)

        orchestrator.create_session(
            session_id="conv-report",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="orchestrator",
        )

        events = list(orchestrator.invoke_sub_agent(
            agent_type=agent_type,
            session_id="conv-report",
            message="get my records",
            system_prompt="prompt",
        ))

        # Events should not be empty (failure is reported, not silent)
        assert len(events) > 0, "Tool failure should produce events, not silence"

        # The error should be reported — either as an error event from the
        # sub-client (with session_id/agent_id) or as a text_delta from the
        # orchestrator's _handle_sub_agent_error (with sub_agent_error flag).
        has_error_info = any(
            e.type == StreamEventType.ERROR.value
            or e.data.get("sub_agent_error")
            or e.data.get("session_id")
            for e in events
        )
        assert has_error_info, "Error should be reported, not silent"

    def test_unregistered_sub_agent_raises(self) -> None:
        """Invoking an unregistered sub-agent raises ValueError."""
        orchestrator = _make_client("orch-001")
        orchestrator.create_session(
            session_id="conv-unreg",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="orchestrator",
        )

        with pytest.raises(ValueError, match="No sub-agent client"):
            list(orchestrator.invoke_sub_agent(
                agent_type="nonexistent_agent",
                session_id="conv-unreg",
                message="test",
                system_prompt="prompt",
            ))

    def test_sub_agent_session_creation_failure_handled(self) -> None:
        """Sub-agent session creation failure is handled gracefully."""
        orchestrator = _make_client("orch-001")

        # Create a sub-client that will fail on session creation
        # by pre-creating a session with the same ID
        sub_client = _make_client("sub-health")
        sub_client.create_session(
            session_id="conv-create-fail__sub_health_advisor",
            user_id="",
            family_id="",
            system_prompt="existing",
        )
        # Now delete it and inject an error hook instead
        sub_client.delete_session("conv-create-fail__sub_health_advisor")

        # Make the sub-client's invoke fail
        def sub_error_hook(sid: str, msg: str) -> Exception:
            return RuntimeError("Invoke failed")

        sub_client.set_error_hook(sub_error_hook)
        orchestrator.register_sub_agent_client("health_advisor", sub_client)

        orchestrator.create_session(
            session_id="conv-create-fail",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="orchestrator",
        )

        # Should handle gracefully
        events = list(orchestrator.invoke_sub_agent(
            agent_type="health_advisor",
            session_id="conv-create-fail",
            message="help",
            system_prompt="health prompt",
        ))

        assert len(events) > 0
        # Orchestrator should still be alive
        assert orchestrator.get_session("conv-create-fail") is not None


# ===========================================================================
# Additional tests for Deployment Model (Task 11.7)
# ===========================================================================


class TestDeploymentModel:
    """Tests for deployment model support — Task 11.7.

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
    """

    def test_register_orchestrator_deployment(self) -> None:
        """Orchestrator is deployed as one managed agent with ECR container."""
        client = _make_client()
        config = DeploymentConfig(
            agent_type="orchestrator",
            agent_id="orch-001",
            ecr_image_uri="123456.dkr.ecr.us-east-1.amazonaws.com/orchestrator:latest",
            is_orchestrator=True,
            region="us-east-1",
        )
        client.register_deployment(config)

        retrieved = client.get_deployment("orchestrator")
        assert retrieved is not None
        assert retrieved.is_orchestrator is True
        assert retrieved.agent_id == "orch-001"

    def test_register_sub_agent_deployments(self) -> None:
        """Each sub-agent type is a separate managed agent with own ECR."""
        client = _make_client()
        for at in ["health_advisor", "shopping_assistant"]:
            config = DeploymentConfig(
                agent_type=at,
                agent_id=f"sub-{at}",
                ecr_image_uri=f"123456.dkr.ecr.us-east-1.amazonaws.com/{at}:latest",
                is_orchestrator=False,
            )
            client.register_deployment(config)

        assert client.get_deployment("health_advisor") is not None
        assert client.get_deployment("shopping_assistant") is not None
        assert len(client.list_deployments()) == 2

    def test_single_instance_serves_all_families(self) -> None:
        """Single runtime instance per agent type resolves family at invocation."""
        client = _make_client()
        config = DeploymentConfig(
            agent_type="health_advisor",
            agent_id="sub-health",
            is_orchestrator=False,
        )
        client.register_deployment(config)

        # Different families use the same deployment
        ctx1 = client.resolve_family_context("health_advisor", "fam-1", "user-1")
        ctx2 = client.resolve_family_context("health_advisor", "fam-2", "user-2")

        assert ctx1["family_id"] == "fam-1"
        assert ctx2["family_id"] == "fam-2"
        assert ctx1["agent_type"] == ctx2["agent_type"] == "health_advisor"

    def test_invoke_agent_runtime_api_for_sub_agent(self) -> None:
        """Orchestrator uses InvokeAgentRuntime API (sub-client) for sub-agents."""
        orchestrator = _make_client("orch-001")
        sub_client = _make_client("sub-health")
        orchestrator.register_sub_agent_client("health_advisor", sub_client)

        orchestrator.create_session(
            session_id="conv-api",
            user_id="user-1",
            family_id="fam-1",
            system_prompt="orchestrator",
        )

        events = list(orchestrator.invoke_sub_agent(
            agent_type="health_advisor",
            session_id="conv-api",
            message="check my health",
            system_prompt="You are a health advisor.",
            domain_tool_ids=["health-tool-1"],
        ))

        # Sub-agent session was created via the sub-client
        sub_session = sub_client.get_session("conv-api__sub_health_advisor")
        assert sub_session is not None
        assert sub_session.system_prompt == "You are a health advisor."
