"""Property-based tests for isolated config construction.

Uses Hypothesis to verify Property 10: Isolated Config Construction.

**Validates: Requirements 3.1, 3.2, 3.3**

Property 10: Isolated Config Construction — for any IsolatedContext with
an active store, the IsolatedMemoryManager should build a MemoryConfig
where family memory_id equals the context's family_store_id (not the
global store), actor_id equals the family_id, and member-tier memory
continues using the shared member store.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.agentcore import IsolatedContext
from app.services.isolated_memory_manager import IsolatedMemoryManager

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-empty, non-whitespace-only strings
_non_empty_str = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())

# A fixed shared member store ID (constant across all families)
SHARED_MEMBER_STORE_ID = "mem-shared-member-store"

# Generate IsolatedContext instances with active stores
_active_context = st.builds(
    IsolatedContext,
    family_id=_non_empty_str,
    member_id=_non_empty_str,
    family_store_id=_non_empty_str,
    is_verified=st.just(True),
    store_status=st.just("active"),
    verified_at=st.just("2025-01-01T00:00:00+00:00"),
)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


class TestIsolatedConfigConstruction:
    """Property 10: Isolated Config Construction.

    **Validates: Requirements 3.1, 3.2, 3.3**
    """

    @given(
        context=_active_context,
        session_id=_non_empty_str,
    )
    @settings(max_examples=50, deadline=None)
    def test_family_config_uses_isolated_store(
        self, context: IsolatedContext, session_id: str
    ) -> None:
        """For any active IsolatedContext, the family config memory_id
        equals context.family_store_id (not a global store) and actor_id
        equals context.family_id.  The member config uses the shared
        member store with actor_id equal to context.member_id.

        This ensures per-family isolation at the config level: each
        family's memory operations target its dedicated store.
        """
        manager = IsolatedMemoryManager(member_memory_id=SHARED_MEMBER_STORE_ID)
        combined = manager.build_isolated_memory_config(context, session_id)

        # Requirement 3.1: family memory_id uses the per-family store
        assert combined.family_config.memory_id == context.family_store_id

        # Requirement 3.2: family actor_id is the family_id
        assert combined.family_config.actor_id == context.family_id

        # Requirement 3.3: member tier uses the shared member store
        assert combined.member_config.memory_id == SHARED_MEMBER_STORE_ID
        assert combined.member_config.memory_id != context.family_store_id

        # Member actor_id is the member_id
        assert combined.member_config.actor_id == context.member_id
