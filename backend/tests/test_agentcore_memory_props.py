"""Property-based tests for AgentCore Memory Manager combined session routing.

Uses Hypothesis to verify Property 9: Combined Session Manager Actor Routing.

**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**

Property 9: Combined Session Manager Actor Routing — for any valid
(family_id, member_id, session_id) triple, family config uses family_id
as actor_id with correct namespaces, member config uses member_id as
actor_id with correct namespaces.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.agentcore import CombinedSessionManager, MemoryConfig
from app.services.agentcore_memory import AgentCoreMemoryManager

# Strategy: non-empty strings that are not whitespace-only
_nonempty_str = st.text(min_size=1).filter(lambda s: s.strip())


class TestCombinedSessionManagerActorRouting:
    """Property 9: Combined Session Manager Actor Routing.

    **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**
    """

    @given(
        family_id=_nonempty_str,
        member_id=_nonempty_str,
        session_id=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_family_config_uses_family_id_as_actor_id(
        self,
        family_id: str,
        member_id: str,
        session_id: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 12.1: family memory store uses family_id as actor_id."""
        if family_mem_id == member_mem_id:
            return  # skip — constructor requires distinct IDs

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        combined = mgr.create_combined_session_manager(
            family_id, member_id, session_id
        )

        assert combined.family_config.actor_id == family_id

    @given(
        family_id=_nonempty_str,
        member_id=_nonempty_str,
        session_id=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_member_config_uses_member_id_as_actor_id(
        self,
        family_id: str,
        member_id: str,
        session_id: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 12.2: member memory store uses member_id as actor_id."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        combined = mgr.create_combined_session_manager(
            family_id, member_id, session_id
        )

        assert combined.member_config.actor_id == member_id

    @given(
        family_id=_nonempty_str,
        member_id=_nonempty_str,
        session_id=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_family_config_has_correct_namespaces(
        self,
        family_id: str,
        member_id: str,
        session_id: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 12.3: family retrieval namespaces are /family/{actorId}/health
        and /family/{actorId}/preferences."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        combined = mgr.create_combined_session_manager(
            family_id, member_id, session_id
        )

        assert combined.family_config.retrieval_namespaces == [
            "/family/{actorId}/health",
            "/family/{actorId}/preferences",
        ]

    @given(
        family_id=_nonempty_str,
        member_id=_nonempty_str,
        session_id=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_member_config_has_correct_namespaces(
        self,
        family_id: str,
        member_id: str,
        session_id: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 12.4: member retrieval namespaces are /member/{actorId}/context
        and /member/{actorId}/summaries/{sessionId}."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        combined = mgr.create_combined_session_manager(
            family_id, member_id, session_id
        )

        assert combined.member_config.retrieval_namespaces == [
            "/member/{actorId}/context",
            "/member/{actorId}/summaries/{sessionId}",
        ]

    @given(
        family_id=_nonempty_str,
        member_id=_nonempty_str,
        session_id=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_family_and_member_configs_use_distinct_memory_store_ids(
        self,
        family_id: str,
        member_id: str,
        session_id: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 13.4: family and member memory stores use distinct IDs."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        combined = mgr.create_combined_session_manager(
            family_id, member_id, session_id
        )

        assert combined.family_config.memory_id != combined.member_config.memory_id

    @given(
        family_id=_nonempty_str,
        member_id=_nonempty_str,
        session_id=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_both_configs_share_same_session_id(
        self,
        family_id: str,
        member_id: str,
        session_id: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Both memory tiers reference the same session_id."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        combined = mgr.create_combined_session_manager(
            family_id, member_id, session_id
        )

        assert combined.family_config.session_id == session_id
        assert combined.member_config.session_id == session_id
        assert combined.session_id == session_id


# ---------------------------------------------------------------------------
# Property 10: Family Memory Persistence
# ---------------------------------------------------------------------------

from app.models.agentcore import CONTENT_MAX_LENGTH, FamilyMemoryCategory, FamilyMemoryRecord

# Strategy: valid category values drawn from the enum
_valid_category = st.sampled_from([c.value for c in FamilyMemoryCategory])

# Strategy: valid subcategory segment (lowercase letters/underscores, non-empty)
_key_segment = st.from_regex(r"[a-z_]+", fullmatch=True).filter(lambda s: len(s) >= 1)

# Strategy: valid identifier segment (alphanumeric, underscores, hyphens, non-empty)
_id_segment = st.from_regex(r"[a-zA-Z0-9_\-]+", fullmatch=True).filter(lambda s: len(s) >= 1)


@st.composite
def valid_memory_key(draw: st.DrawFn) -> str:
    """Generate a valid hierarchical memory_key: {category}/{subcategory}/{id}."""
    cat = draw(_valid_category)
    sub = draw(_key_segment)
    ident = draw(_id_segment)
    return f"{cat}/{sub}/{ident}"


# Strategy: content within the max length
_valid_content = st.text(min_size=1, max_size=CONTENT_MAX_LENGTH).filter(
    lambda s: s.strip()
)


class TestFamilyMemoryPersistence:
    """Property 10: Family Memory Persistence.

    **Validates: Requirements 14.1, 14.2, 14.3, 14.4, 14.5**

    For any family memory record, it persists without TTL, category is valid,
    content ≤ 10000 chars, memory_key follows format.
    """

    @given(
        family_id=_nonempty_str,
        memory_key=valid_memory_key(),
        category=_valid_category,
        content=_valid_content,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_stored_record_has_no_ttl(
        self,
        family_id: str,
        memory_key: str,
        category: str,
        content: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 14.1: family memory records persist without TTL (no expiry)."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        record = mgr.store_family_memory(family_id, memory_key, category, content)

        assert record.ttl is None

    @given(
        family_id=_nonempty_str,
        memory_key=valid_memory_key(),
        category=_valid_category,
        content=_valid_content,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_stored_record_has_valid_category(
        self,
        family_id: str,
        memory_key: str,
        category: str,
        content: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 14.3: category is one of health/preferences/context."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        record = mgr.store_family_memory(family_id, memory_key, category, content)

        valid_categories = {c.value for c in FamilyMemoryCategory}
        assert record.category in valid_categories

    @given(
        family_id=_nonempty_str,
        memory_key=valid_memory_key(),
        category=_valid_category,
        content=_valid_content,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_stored_record_content_within_limit(
        self,
        family_id: str,
        memory_key: str,
        category: str,
        content: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 14.4: content length ≤ 10000 chars."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        record = mgr.store_family_memory(family_id, memory_key, category, content)

        assert len(record.content) <= CONTENT_MAX_LENGTH

    @given(
        family_id=_nonempty_str,
        memory_key=valid_memory_key(),
        category=_valid_category,
        content=_valid_content,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_stored_record_memory_key_follows_format(
        self,
        family_id: str,
        memory_key: str,
        category: str,
        content: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 14.5: memory_key follows hierarchical format with at least 2 slashes."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        record = mgr.store_family_memory(family_id, memory_key, category, content)

        parts = record.memory_key.split("/")
        assert len(parts) >= 3, f"memory_key must have at least 2 '/' separators, got: {record.memory_key}"

    @given(
        family_id=_nonempty_str,
        memory_key=valid_memory_key(),
        category=_valid_category,
        content=_valid_content,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_stored_record_can_be_retrieved(
        self,
        family_id: str,
        memory_key: str,
        category: str,
        content: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 14.2: stored records can be retrieved and match what was stored."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        stored = mgr.store_family_memory(family_id, memory_key, category, content)
        retrieved = mgr.retrieve_family_memory(family_id)

        assert len(retrieved) >= 1
        match = [r for r in retrieved if r.memory_key == memory_key]
        assert len(match) == 1
        assert match[0].family_id == stored.family_id
        assert match[0].category == stored.category
        assert match[0].content == stored.content
        assert match[0].ttl is None

    @given(
        family_id_a=_nonempty_str,
        family_id_b=_nonempty_str,
        memory_key=valid_memory_key(),
        category=_valid_category,
        content=_valid_content,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_records_isolated_between_families(
        self,
        family_id_a: str,
        family_id_b: str,
        memory_key: str,
        category: str,
        content: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Records for different families are isolated."""
        if family_mem_id == member_mem_id:
            return
        if family_id_a == family_id_b:
            return  # need distinct families to test isolation

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        mgr.store_family_memory(family_id_a, memory_key, category, content)

        retrieved_b = mgr.retrieve_family_memory(family_id_b)
        assert len(retrieved_b) == 0, (
            f"Family {family_id_b} should not see records from family {family_id_a}"
        )


# ---------------------------------------------------------------------------
# Property 11: Member Memory Expiry
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone

from app.models.agentcore import MemberMemoryRecord


class TestMemberMemoryExpiry:
    """Property 11: Member Memory Expiry.

    **Validates: Requirements 15.1, 15.2, 15.3, 31.1**

    For any member memory record, TTL is 30 days from creation, scoped by
    member_id and session_id, message_count increments on interaction.
    """

    @given(
        member_id=_nonempty_str,
        session_id=_nonempty_str,
        content=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_ttl_is_30_days_from_created_at(
        self,
        member_id: str,
        session_id: str,
        content: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 15.1: TTL is exactly 30 days from created_at timestamp."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        record = mgr.store_member_memory(member_id, session_id, content)

        created_at = datetime.fromisoformat(record.created_at)
        expected_ttl = int((created_at + timedelta(days=30)).timestamp())
        assert record.ttl == expected_ttl

    @given(
        member_id=_nonempty_str,
        session_id_a=_nonempty_str,
        session_id_b=_nonempty_str,
        content=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_records_scoped_by_member_and_session(
        self,
        member_id: str,
        session_id_a: str,
        session_id_b: str,
        content: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 15.2: records are scoped by (member_id, session_id) — different
        sessions for the same member are separate records."""
        if family_mem_id == member_mem_id:
            return
        if session_id_a == session_id_b:
            return  # need distinct sessions

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        rec_a = mgr.store_member_memory(member_id, session_id_a, content)
        rec_b = mgr.store_member_memory(member_id, session_id_b, content)

        retrieved = mgr.retrieve_member_memory(member_id)
        session_ids = {r.session_id for r in retrieved}
        assert session_id_a in session_ids
        assert session_id_b in session_ids
        assert len(retrieved) >= 2
        # Each record is independent
        assert rec_a.session_id != rec_b.session_id

    @given(
        member_id=_nonempty_str,
        session_id=_nonempty_str,
        content=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_message_count_starts_at_one_and_increments(
        self,
        member_id: str,
        session_id: str,
        content: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 15.3: message_count starts at 1 and increments by 1 on each
        subsequent store for the same (member_id, session_id)."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)

        rec1 = mgr.store_member_memory(member_id, session_id, content)
        assert rec1.message_count == 1

        rec2 = mgr.store_member_memory(member_id, session_id, content)
        assert rec2.message_count == 2

        rec3 = mgr.store_member_memory(member_id, session_id, content)
        assert rec3.message_count == 3

    @given(
        member_id_a=_nonempty_str,
        member_id_b=_nonempty_str,
        session_id=_nonempty_str,
        content=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_different_members_same_session_independent(
        self,
        member_id_a: str,
        member_id_b: str,
        session_id: str,
        content: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Different members with the same session_id have independent records
        and counts."""
        if family_mem_id == member_mem_id:
            return
        if member_id_a == member_id_b:
            return  # need distinct members

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)

        # Store twice for member A, once for member B — same session_id
        mgr.store_member_memory(member_id_a, session_id, content)
        rec_a2 = mgr.store_member_memory(member_id_a, session_id, content)
        rec_b1 = mgr.store_member_memory(member_id_b, session_id, content)

        assert rec_a2.message_count == 2
        assert rec_b1.message_count == 1

        # Retrieval is isolated per member
        retrieved_a = mgr.retrieve_member_memory(member_id_a)
        retrieved_b = mgr.retrieve_member_memory(member_id_b)
        assert all(r.member_id == member_id_a for r in retrieved_a)
        assert all(r.member_id == member_id_b for r in retrieved_b)

    @given(
        member_id=_nonempty_str,
        session_id=_nonempty_str,
        content=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_ttl_stays_relative_to_original_creation(
        self,
        member_id: str,
        session_id: str,
        content: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """TTL stays relative to original creation (doesn't change on updates)."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)

        rec1 = mgr.store_member_memory(member_id, session_id, content)
        original_ttl = rec1.ttl
        original_created_at = rec1.created_at

        # Update the same record multiple times
        rec2 = mgr.store_member_memory(member_id, session_id, content)
        rec3 = mgr.store_member_memory(member_id, session_id, content)

        # TTL must remain the same (based on original creation)
        assert rec2.ttl == original_ttl
        assert rec3.ttl == original_ttl
        # created_at must not change
        assert rec2.created_at == original_created_at
        assert rec3.created_at == original_created_at


# ---------------------------------------------------------------------------
# Property 7: Memory Tier Isolation
# ---------------------------------------------------------------------------


class TestMemoryTierIsolation:
    """Property 7: Memory Tier Isolation.

    **Validates: Requirements 13.1, 13.2, 13.3, 13.4**

    For any family_id and member_id, family memory queries never return
    member records and vice versa; distinct store IDs.
    """

    @given(
        family_id=_nonempty_str,
        member_id=_nonempty_str,
        memory_key=valid_memory_key(),
        category=_valid_category,
        content=_valid_content,
        session_id=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_family_retrieval_never_returns_member_records(
        self,
        family_id: str,
        member_id: str,
        memory_key: str,
        category: str,
        content: str,
        session_id: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 13.2: querying family memory returns only FamilyMemoryRecord
        instances, never MemberMemoryRecord."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        mgr.store_family_memory(family_id, memory_key, category, content)
        mgr.store_member_memory(member_id, session_id, content)

        family_records = mgr.retrieve_family_memory(family_id)
        for rec in family_records:
            assert isinstance(rec, FamilyMemoryRecord), (
                f"Expected FamilyMemoryRecord, got {type(rec).__name__}"
            )
            assert not isinstance(rec, MemberMemoryRecord), (
                "Family retrieval must never return MemberMemoryRecord"
            )

    @given(
        family_id=_nonempty_str,
        member_id=_nonempty_str,
        memory_key=valid_memory_key(),
        category=_valid_category,
        content=_valid_content,
        session_id=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_member_retrieval_never_returns_family_records(
        self,
        family_id: str,
        member_id: str,
        memory_key: str,
        category: str,
        content: str,
        session_id: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 13.3: querying member memory returns only MemberMemoryRecord
        instances, never FamilyMemoryRecord."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        mgr.store_family_memory(family_id, memory_key, category, content)
        mgr.store_member_memory(member_id, session_id, content)

        member_records = mgr.retrieve_member_memory(member_id)
        for rec in member_records:
            assert isinstance(rec, MemberMemoryRecord), (
                f"Expected MemberMemoryRecord, got {type(rec).__name__}"
            )
            assert not isinstance(rec, FamilyMemoryRecord), (
                "Member retrieval must never return FamilyMemoryRecord"
            )

    @given(
        family_id=_nonempty_str,
        member_id=_nonempty_str,
        memory_key=valid_memory_key(),
        category=_valid_category,
        content=_valid_content,
        session_id=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_cross_tier_family_to_member_returns_empty(
        self,
        family_id: str,
        member_id: str,
        memory_key: str,
        category: str,
        content: str,
        session_id: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 13.1, 13.3: storing in family tier and querying member tier
        returns nothing (cross-tier isolation)."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        mgr.store_family_memory(family_id, memory_key, category, content)

        # Member retrieval must be empty — family records are invisible
        member_records = mgr.retrieve_member_memory(member_id)
        assert len(member_records) == 0, (
            f"Member retrieval should be empty after storing only family memory, "
            f"got {len(member_records)} records"
        )

    @given(
        family_id=_nonempty_str,
        member_id=_nonempty_str,
        content=_nonempty_str,
        session_id=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_cross_tier_member_to_family_returns_empty(
        self,
        family_id: str,
        member_id: str,
        content: str,
        session_id: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 13.1, 13.2: storing in member tier and querying family tier
        returns nothing (cross-tier isolation)."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        mgr.store_member_memory(member_id, session_id, content)

        # Family retrieval must be empty — member records are invisible
        family_records = mgr.retrieve_family_memory(family_id)
        assert len(family_records) == 0, (
            f"Family retrieval should be empty after storing only member memory, "
            f"got {len(family_records)} records"
        )

    @given(
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_family_and_member_stores_use_distinct_memory_ids(
        self,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 13.4: family and member memory stores use distinct IDs."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        assert mgr.family_memory_id != mgr.member_memory_id, (
            "Family and member memory store IDs must be distinct"
        )


# ---------------------------------------------------------------------------
# Property 12: Family Scope Correctness
# ---------------------------------------------------------------------------


class TestFamilyScopeCorrectness:
    """Property 12: Family Scope Correctness.

    **Validates: Requirements 16.1, 16.2, 16.3**

    For any user, combined retrieval includes all family records for their
    family_id and only their own member records; excludes other members'
    records.
    """

    @given(
        family_id=_nonempty_str,
        member_id=_nonempty_str,
        memory_key=valid_memory_key(),
        category=_valid_category,
        content=_valid_content,
        session_id=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_family_retrieval_returns_all_records_for_family_id(
        self,
        family_id: str,
        member_id: str,
        memory_key: str,
        category: str,
        content: str,
        session_id: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 16.1: retrieving family memory returns all records matching
        the user's family_id."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)

        # Store a family record and a member record
        mgr.store_family_memory(family_id, memory_key, category, content)
        mgr.store_member_memory(member_id, session_id, content)

        # Family retrieval must include the family record
        family_records = mgr.retrieve_family_memory(family_id)
        assert len(family_records) >= 1
        assert all(r.family_id == family_id for r in family_records)
        keys = {r.memory_key for r in family_records}
        assert memory_key in keys

    @given(
        member_id=_nonempty_str,
        other_member_id=_nonempty_str,
        session_id=_nonempty_str,
        other_session_id=_nonempty_str,
        content=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_member_retrieval_returns_only_own_records(
        self,
        member_id: str,
        other_member_id: str,
        session_id: str,
        other_session_id: str,
        content: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 16.2: retrieving member memory returns only records matching
        the user's own member_id, not other members'."""
        if family_mem_id == member_mem_id:
            return
        if member_id == other_member_id:
            return  # need distinct members

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)

        # Both members store records
        mgr.store_member_memory(member_id, session_id, content)
        mgr.store_member_memory(other_member_id, other_session_id, content)

        # Retrieval for member_id returns only their records
        records = mgr.retrieve_member_memory(member_id)
        assert len(records) >= 1
        assert all(r.member_id == member_id for r in records)

    @given(
        family_id=_nonempty_str,
        member_a=_nonempty_str,
        member_b=_nonempty_str,
        memory_key=valid_memory_key(),
        category=_valid_category,
        content=_valid_content,
        session_a=_nonempty_str,
        session_b=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_same_family_members_see_same_family_different_member_records(
        self,
        family_id: str,
        member_a: str,
        member_b: str,
        memory_key: str,
        category: str,
        content: str,
        session_a: str,
        session_b: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 16.1, 16.2: two members in the same family both see the same
        family records but different member records."""
        if family_mem_id == member_mem_id:
            return
        if member_a == member_b:
            return  # need distinct members

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)

        # Store shared family record
        mgr.store_family_memory(family_id, memory_key, category, content)
        # Each member stores their own member record
        mgr.store_member_memory(member_a, session_a, "member_a context")
        mgr.store_member_memory(member_b, session_b, "member_b context")

        # Both members see the same family records
        family_for_a = mgr.retrieve_family_memory(family_id)
        family_for_b = mgr.retrieve_family_memory(family_id)
        assert len(family_for_a) == len(family_for_b)
        assert {r.memory_key for r in family_for_a} == {r.memory_key for r in family_for_b}

        # Each member sees only their own member records
        member_a_records = mgr.retrieve_member_memory(member_a)
        member_b_records = mgr.retrieve_member_memory(member_b)
        assert all(r.member_id == member_a for r in member_a_records)
        assert all(r.member_id == member_b for r in member_b_records)

    @given(
        member_id=_nonempty_str,
        other_member_id=_nonempty_str,
        session_id=_nonempty_str,
        content=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_member_records_invisible_to_other_members(
        self,
        member_id: str,
        other_member_id: str,
        session_id: str,
        content: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 16.3: a member's records are invisible to other members via
        retrieve_member_memory."""
        if family_mem_id == member_mem_id:
            return
        if member_id == other_member_id:
            return  # need distinct members

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)

        # Only member_id stores a record
        mgr.store_member_memory(member_id, session_id, content)

        # other_member_id must not see it
        other_records = mgr.retrieve_member_memory(other_member_id)
        assert len(other_records) == 0, (
            f"Member {other_member_id} should not see records from {member_id}, "
            f"got {len(other_records)} records"
        )


# ---------------------------------------------------------------------------
# Property 20: Memory Graceful Degradation
# ---------------------------------------------------------------------------

from unittest.mock import patch


class TestMemoryGracefulDegradation:
    """Property 20: Memory Graceful Degradation.

    **Validates: Requirements 22.1, 22.3**

    For any memory service failure during retrieval, system logs warning
    and proceeds without memory context in stateless mode.
    """

    @given(
        family_id=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_unavailable_safe_retrieve_family_returns_empty(
        self,
        family_id: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 22.1, 22.3: when memory service is unavailable,
        safe_retrieve_family_memory returns an empty list."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        mgr.set_available(False)

        result = mgr.safe_retrieve_family_memory(family_id)

        assert result == []
        assert isinstance(result, list)

    @given(
        member_id=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_unavailable_safe_retrieve_member_returns_empty(
        self,
        member_id: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 22.1, 22.3: when memory service is unavailable,
        safe_retrieve_member_memory returns an empty list."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        mgr.set_available(False)

        result = mgr.safe_retrieve_member_memory(member_id)

        assert result == []
        assert isinstance(result, list)

    @given(
        family_id=_nonempty_str,
        memory_key=valid_memory_key(),
        category=_valid_category,
        content=_valid_content,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_unavailable_safe_store_family_returns_none_no_queue(
        self,
        family_id: str,
        memory_key: str,
        category: str,
        content: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 22.3: when memory service is unavailable,
        safe_store_family_memory returns None and does NOT queue."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        mgr.set_available(False)

        result = mgr.safe_store_family_memory(family_id, memory_key, category, content)

        assert result is None
        assert mgr.get_retry_queue() == []

    @given(
        member_id=_nonempty_str,
        session_id=_nonempty_str,
        content=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_unavailable_safe_store_member_returns_none_no_queue(
        self,
        member_id: str,
        session_id: str,
        content: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 22.3: when memory service is unavailable,
        safe_store_member_memory returns None and does NOT queue."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        mgr.set_available(False)

        result = mgr.safe_store_member_memory(member_id, session_id, content)

        assert result is None
        assert mgr.get_retry_queue() == []

    @given(
        family_id=_nonempty_str,
        member_id=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_exception_during_retrieval_returns_empty(
        self,
        family_id: str,
        member_id: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 22.1: when retrieval raises an exception,
        safe_retrieve returns empty list (graceful degradation)."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        # Service is available but the underlying call raises
        assert mgr.is_available

        with patch.object(
            mgr, "retrieve_family_memory", side_effect=RuntimeError("connection lost")
        ):
            family_result = mgr.safe_retrieve_family_memory(family_id)
        assert family_result == []

        with patch.object(
            mgr, "retrieve_member_memory", side_effect=RuntimeError("connection lost")
        ):
            member_result = mgr.safe_retrieve_member_memory(member_id)
        assert member_result == []

    @given(
        family_id=_nonempty_str,
        memory_key=valid_memory_key(),
        category=_valid_category,
        content=_valid_content,
        member_id=_nonempty_str,
        session_id=_nonempty_str,
        family_mem_id=_nonempty_str,
        member_mem_id=_nonempty_str,
    )
    @settings(max_examples=10)
    def test_exception_during_store_returns_none_and_queues(
        self,
        family_id: str,
        memory_key: str,
        category: str,
        content: str,
        member_id: str,
        session_id: str,
        family_mem_id: str,
        member_mem_id: str,
    ) -> None:
        """Req 22.1: when store raises an exception,
        safe_store returns None and queues for retry."""
        if family_mem_id == member_mem_id:
            return

        mgr = AgentCoreMemoryManager(family_mem_id, member_mem_id)
        assert mgr.is_available

        # Family store exception → queued
        with patch.object(
            mgr, "store_family_memory", side_effect=RuntimeError("write failed")
        ):
            fam_result = mgr.safe_store_family_memory(
                family_id, memory_key, category, content
            )
        assert fam_result is None
        queue = mgr.get_retry_queue()
        assert len(queue) == 1
        assert queue[0]["operation"] == "store_family_memory"

        # Member store exception → queued
        with patch.object(
            mgr, "store_member_memory", side_effect=RuntimeError("write failed")
        ):
            mem_result = mgr.safe_store_member_memory(member_id, session_id, content)
        assert mem_result is None
        queue = mgr.get_retry_queue()
        assert len(queue) == 2
        assert queue[1]["operation"] == "store_member_memory"
