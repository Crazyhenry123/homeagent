"""Tests for AgentCoreMemoryManager dual-tier memory configuration."""

import pytest

from app.models.agentcore import MemberMemoryRecord, MemoryConfig
from app.services.agentcore_memory import AgentCoreMemoryManager


FAMILY_MEM_ID = "mem-family-store-001"
MEMBER_MEM_ID = "mem-member-store-002"


@pytest.fixture()
def manager():
    return AgentCoreMemoryManager(FAMILY_MEM_ID, MEMBER_MEM_ID)


# ── Constructor validation ──────────────────────────────────────────────


class TestConstructorValidation:
    def test_rejects_empty_family_memory_id(self):
        with pytest.raises(ValueError, match="family_memory_id"):
            AgentCoreMemoryManager("", MEMBER_MEM_ID)

    def test_rejects_empty_member_memory_id(self):
        with pytest.raises(ValueError, match="member_memory_id"):
            AgentCoreMemoryManager(FAMILY_MEM_ID, "")

    def test_rejects_identical_memory_ids(self):
        with pytest.raises(ValueError, match="distinct"):
            AgentCoreMemoryManager("same-id", "same-id")

    def test_stores_memory_ids(self, manager):
        assert manager.family_memory_id == FAMILY_MEM_ID
        assert manager.member_memory_id == MEMBER_MEM_ID


# ── get_family_memory_config ────────────────────────────────────────────


class TestGetFamilyMemoryConfig:
    def test_returns_memory_config(self, manager):
        config = manager.get_family_memory_config("fam_123", "sess_abc")
        assert isinstance(config, MemoryConfig)

    def test_uses_family_memory_id(self, manager):
        config = manager.get_family_memory_config("fam_123", "sess_abc")
        assert config.memory_id == FAMILY_MEM_ID

    def test_uses_family_id_as_actor_id(self, manager):
        config = manager.get_family_memory_config("fam_123", "sess_abc")
        assert config.actor_id == "fam_123"

    def test_sets_session_id(self, manager):
        config = manager.get_family_memory_config("fam_123", "sess_abc")
        assert config.session_id == "sess_abc"

    def test_has_correct_namespaces(self, manager):
        config = manager.get_family_memory_config("fam_123", "sess_abc")
        assert config.retrieval_namespaces == [
            "/family/{actorId}/health",
            "/family/{actorId}/preferences",
        ]

    def test_config_validates(self, manager):
        config = manager.get_family_memory_config("fam_123", "sess_abc")
        config.validate()  # should not raise

    def test_rejects_empty_family_id(self, manager):
        with pytest.raises(ValueError, match="family_id"):
            manager.get_family_memory_config("", "sess_abc")

    def test_rejects_empty_session_id(self, manager):
        with pytest.raises(ValueError, match="session_id"):
            manager.get_family_memory_config("fam_123", "")


# ── get_member_memory_config ────────────────────────────────────────────


class TestGetMemberMemoryConfig:
    def test_returns_memory_config(self, manager):
        config = manager.get_member_memory_config("usr_456", "sess_abc")
        assert isinstance(config, MemoryConfig)

    def test_uses_member_memory_id(self, manager):
        config = manager.get_member_memory_config("usr_456", "sess_abc")
        assert config.memory_id == MEMBER_MEM_ID

    def test_uses_member_id_as_actor_id(self, manager):
        config = manager.get_member_memory_config("usr_456", "sess_abc")
        assert config.actor_id == "usr_456"

    def test_sets_session_id(self, manager):
        config = manager.get_member_memory_config("usr_456", "sess_abc")
        assert config.session_id == "sess_abc"

    def test_has_correct_namespaces(self, manager):
        config = manager.get_member_memory_config("usr_456", "sess_abc")
        assert config.retrieval_namespaces == [
            "/member/{actorId}/context",
            "/member/{actorId}/summaries/{sessionId}",
        ]

    def test_config_validates(self, manager):
        config = manager.get_member_memory_config("usr_456", "sess_abc")
        config.validate()  # should not raise

    def test_rejects_empty_member_id(self, manager):
        with pytest.raises(ValueError, match="member_id"):
            manager.get_member_memory_config("", "sess_abc")

    def test_rejects_empty_session_id(self, manager):
        with pytest.raises(ValueError, match="session_id"):
            manager.get_member_memory_config("usr_456", "")


# ── Tier isolation ──────────────────────────────────────────────────────


class TestTierIsolation:
    def test_family_and_member_use_distinct_memory_ids(self, manager):
        family_cfg = manager.get_family_memory_config("fam_1", "s1")
        member_cfg = manager.get_member_memory_config("usr_1", "s1")
        assert family_cfg.memory_id != member_cfg.memory_id

    def test_family_and_member_use_different_actor_ids(self, manager):
        family_cfg = manager.get_family_memory_config("fam_1", "s1")
        member_cfg = manager.get_member_memory_config("usr_1", "s1")
        assert family_cfg.actor_id == "fam_1"
        assert member_cfg.actor_id == "usr_1"

    def test_namespaces_do_not_overlap(self, manager):
        family_cfg = manager.get_family_memory_config("fam_1", "s1")
        member_cfg = manager.get_member_memory_config("usr_1", "s1")
        family_ns = set(family_cfg.retrieval_namespaces)
        member_ns = set(member_cfg.retrieval_namespaces)
        assert family_ns.isdisjoint(member_ns)


# ── create_combined_session_manager ─────────────────────────────────────


class TestCreateCombinedSessionManager:
    def test_returns_combined_session_manager(self, manager):
        from app.models.agentcore import CombinedSessionManager

        result = manager.create_combined_session_manager("fam_1", "usr_1", "sess_1")
        assert isinstance(result, CombinedSessionManager)

    def test_family_config_uses_family_id_as_actor(self, manager):
        result = manager.create_combined_session_manager("fam_1", "usr_1", "sess_1")
        assert result.family_config.actor_id == "fam_1"

    def test_member_config_uses_member_id_as_actor(self, manager):
        result = manager.create_combined_session_manager("fam_1", "usr_1", "sess_1")
        assert result.member_config.actor_id == "usr_1"

    def test_family_config_uses_family_memory_id(self, manager):
        result = manager.create_combined_session_manager("fam_1", "usr_1", "sess_1")
        assert result.family_config.memory_id == FAMILY_MEM_ID

    def test_member_config_uses_member_memory_id(self, manager):
        result = manager.create_combined_session_manager("fam_1", "usr_1", "sess_1")
        assert result.member_config.memory_id == MEMBER_MEM_ID

    def test_configs_use_distinct_memory_ids(self, manager):
        result = manager.create_combined_session_manager("fam_1", "usr_1", "sess_1")
        assert result.family_config.memory_id != result.member_config.memory_id

    def test_sets_family_id(self, manager):
        result = manager.create_combined_session_manager("fam_1", "usr_1", "sess_1")
        assert result.family_id == "fam_1"

    def test_sets_member_id(self, manager):
        result = manager.create_combined_session_manager("fam_1", "usr_1", "sess_1")
        assert result.member_id == "usr_1"

    def test_sets_session_id(self, manager):
        result = manager.create_combined_session_manager("fam_1", "usr_1", "sess_1")
        assert result.session_id == "sess_1"

    def test_both_configs_share_session_id(self, manager):
        result = manager.create_combined_session_manager("fam_1", "usr_1", "sess_1")
        assert result.family_config.session_id == "sess_1"
        assert result.member_config.session_id == "sess_1"

    def test_family_config_has_correct_namespaces(self, manager):
        result = manager.create_combined_session_manager("fam_1", "usr_1", "sess_1")
        assert result.family_config.retrieval_namespaces == [
            "/family/{actorId}/health",
            "/family/{actorId}/preferences",
        ]

    def test_member_config_has_correct_namespaces(self, manager):
        result = manager.create_combined_session_manager("fam_1", "usr_1", "sess_1")
        assert result.member_config.retrieval_namespaces == [
            "/member/{actorId}/context",
            "/member/{actorId}/summaries/{sessionId}",
        ]

    def test_result_passes_validation(self, manager):
        result = manager.create_combined_session_manager("fam_1", "usr_1", "sess_1")
        result.validate()  # should not raise

    def test_rejects_empty_family_id(self, manager):
        with pytest.raises(ValueError, match="family_id"):
            manager.create_combined_session_manager("", "usr_1", "sess_1")

    def test_rejects_whitespace_family_id(self, manager):
        with pytest.raises(ValueError, match="family_id"):
            manager.create_combined_session_manager("   ", "usr_1", "sess_1")

    def test_rejects_empty_member_id(self, manager):
        with pytest.raises(ValueError, match="member_id"):
            manager.create_combined_session_manager("fam_1", "", "sess_1")

    def test_rejects_whitespace_member_id(self, manager):
        with pytest.raises(ValueError, match="member_id"):
            manager.create_combined_session_manager("fam_1", "   ", "sess_1")

    def test_rejects_empty_session_id(self, manager):
        with pytest.raises(ValueError, match="session_id"):
            manager.create_combined_session_manager("fam_1", "usr_1", "")

    def test_rejects_whitespace_session_id(self, manager):
        with pytest.raises(ValueError, match="session_id"):
            manager.create_combined_session_manager("fam_1", "usr_1", "   ")


# ── store_family_memory ─────────────────────────────────────────────────


class TestStoreFamilyMemory:
    def test_stores_and_returns_record(self, manager):
        record = manager.store_family_memory(
            family_id="fam_1",
            memory_key="health/allergy/peanut",
            category="health",
            content="Alice has a peanut allergy",
        )
        assert record.family_id == "fam_1"
        assert record.memory_key == "health/allergy/peanut"
        assert record.category == "health"
        assert record.content == "Alice has a peanut allergy"

    def test_record_has_no_ttl(self, manager):
        record = manager.store_family_memory(
            family_id="fam_1",
            memory_key="health/allergy/peanut",
            category="health",
            content="Peanut allergy",
        )
        assert record.ttl is None

    def test_record_has_timestamps(self, manager):
        record = manager.store_family_memory(
            family_id="fam_1",
            memory_key="health/allergy/peanut",
            category="health",
            content="Peanut allergy",
        )
        assert record.created_at != ""
        assert record.updated_at != ""

    def test_record_uses_family_memory_id(self, manager):
        record = manager.store_family_memory(
            family_id="fam_1",
            memory_key="health/allergy/peanut",
            category="health",
            content="Peanut allergy",
        )
        assert record.agentcore_memory_id == FAMILY_MEM_ID

    def test_accepts_health_category(self, manager):
        record = manager.store_family_memory(
            family_id="fam_1",
            memory_key="health/allergy/peanut",
            category="health",
            content="data",
        )
        assert record.category == "health"

    def test_accepts_preferences_category(self, manager):
        record = manager.store_family_memory(
            family_id="fam_1",
            memory_key="preferences/diet/vegetarian",
            category="preferences",
            content="data",
        )
        assert record.category == "preferences"

    def test_accepts_context_category(self, manager):
        record = manager.store_family_memory(
            family_id="fam_1",
            memory_key="context/general/info1",
            category="context",
            content="data",
        )
        assert record.category == "context"

    def test_rejects_invalid_category(self, manager):
        with pytest.raises(ValueError, match="category"):
            manager.store_family_memory(
                family_id="fam_1",
                memory_key="health/allergy/peanut",
                category="invalid",
                content="data",
            )

    def test_rejects_content_over_10000_chars(self, manager):
        with pytest.raises(ValueError, match="maximum length"):
            manager.store_family_memory(
                family_id="fam_1",
                memory_key="health/allergy/peanut",
                category="health",
                content="x" * 10_001,
            )

    def test_accepts_content_at_10000_chars(self, manager):
        record = manager.store_family_memory(
            family_id="fam_1",
            memory_key="health/allergy/peanut",
            category="health",
            content="x" * 10_000,
        )
        assert len(record.content) == 10_000

    def test_rejects_invalid_memory_key_format(self, manager):
        with pytest.raises(ValueError, match="memory_key"):
            manager.store_family_memory(
                family_id="fam_1",
                memory_key="bad-key",
                category="health",
                content="data",
            )

    def test_rejects_empty_family_id(self, manager):
        with pytest.raises(ValueError, match="family_id"):
            manager.store_family_memory(
                family_id="",
                memory_key="health/allergy/peanut",
                category="health",
                content="data",
            )

    def test_update_preserves_created_at(self, manager):
        first = manager.store_family_memory(
            family_id="fam_1",
            memory_key="health/allergy/peanut",
            category="health",
            content="v1",
        )
        second = manager.store_family_memory(
            family_id="fam_1",
            memory_key="health/allergy/peanut",
            category="health",
            content="v2",
        )
        assert second.created_at == first.created_at
        assert second.content == "v2"

    def test_stores_source_member_id(self, manager):
        record = manager.store_family_memory(
            family_id="fam_1",
            memory_key="health/allergy/peanut",
            category="health",
            content="data",
            source_member_id="usr_42",
        )
        assert record.source_member_id == "usr_42"


# ── retrieve_family_memory ──────────────────────────────────────────────


class TestRetrieveFamilyMemory:
    def test_returns_empty_list_when_no_records(self, manager):
        result = manager.retrieve_family_memory("fam_1")
        assert result == []

    def test_returns_stored_records(self, manager):
        manager.store_family_memory(
            family_id="fam_1",
            memory_key="health/allergy/peanut",
            category="health",
            content="Peanut allergy",
        )
        result = manager.retrieve_family_memory("fam_1")
        assert len(result) == 1
        assert result[0].content == "Peanut allergy"

    def test_returns_only_records_for_requested_family(self, manager):
        manager.store_family_memory(
            family_id="fam_1",
            memory_key="health/allergy/peanut",
            category="health",
            content="fam_1 data",
        )
        manager.store_family_memory(
            family_id="fam_2",
            memory_key="health/allergy/gluten",
            category="health",
            content="fam_2 data",
        )
        result = manager.retrieve_family_memory("fam_1")
        assert len(result) == 1
        assert result[0].family_id == "fam_1"

    def test_returns_multiple_records_for_same_family(self, manager):
        manager.store_family_memory(
            family_id="fam_1",
            memory_key="health/allergy/peanut",
            category="health",
            content="allergy",
        )
        manager.store_family_memory(
            family_id="fam_1",
            memory_key="preferences/diet/vegetarian",
            category="preferences",
            content="diet pref",
        )
        result = manager.retrieve_family_memory("fam_1")
        assert len(result) == 2

    def test_rejects_empty_family_id(self, manager):
        with pytest.raises(ValueError, match="family_id"):
            manager.retrieve_family_memory("")

    def test_rejects_whitespace_family_id(self, manager):
        with pytest.raises(ValueError, match="family_id"):
            manager.retrieve_family_memory("   ")

# ── Member short-term memory tests ──────────────────────────────────────


class TestStoreMemberMemory:
    def test_stores_and_returns_record(self, manager):
        record = manager.store_member_memory("mem_1", "sess_1", "hello context")
        assert record.member_id == "mem_1"
        assert record.session_id == "sess_1"
        assert record.summary == "hello context"

    def test_record_has_30_day_ttl(self, manager):
        record = manager.store_member_memory("mem_1", "sess_1", "ctx")
        assert record.ttl is not None
        # TTL should be ~30 days from now (within a small tolerance)
        from datetime import datetime, timedelta, timezone

        created = datetime.fromisoformat(record.created_at)
        expected_ttl = int((created + timedelta(days=30)).timestamp())
        assert record.ttl == expected_ttl

    def test_message_count_starts_at_one(self, manager):
        record = manager.store_member_memory("mem_1", "sess_1", "ctx")
        assert record.message_count == 1

    def test_message_count_increments(self, manager):
        manager.store_member_memory("mem_1", "sess_1", "first")
        record2 = manager.store_member_memory("mem_1", "sess_1", "second")
        assert record2.message_count == 2
        record3 = manager.store_member_memory("mem_1", "sess_1", "third")
        assert record3.message_count == 3

    def test_update_preserves_created_at(self, manager):
        r1 = manager.store_member_memory("mem_1", "sess_1", "first")
        r2 = manager.store_member_memory("mem_1", "sess_1", "second")
        assert r2.created_at == r1.created_at

    def test_update_changes_updated_at(self, manager):
        r1 = manager.store_member_memory("mem_1", "sess_1", "first")
        r2 = manager.store_member_memory("mem_1", "sess_1", "second")
        # updated_at should be >= created_at (may be equal if fast)
        assert r2.updated_at >= r1.created_at

    def test_ttl_stays_relative_to_original_creation(self, manager):
        r1 = manager.store_member_memory("mem_1", "sess_1", "first")
        r2 = manager.store_member_memory("mem_1", "sess_1", "second")
        # TTL should be the same since it's based on original created_at
        assert r2.ttl == r1.ttl

    def test_record_uses_member_memory_id(self, manager):
        record = manager.store_member_memory("mem_1", "sess_1", "ctx")
        assert record.agentcore_memory_id == "mem-member-store-002"

    def test_record_has_timestamps(self, manager):
        record = manager.store_member_memory("mem_1", "sess_1", "ctx")
        assert record.created_at != ""
        assert record.updated_at != ""

    def test_different_sessions_have_separate_counts(self, manager):
        manager.store_member_memory("mem_1", "sess_1", "a")
        manager.store_member_memory("mem_1", "sess_1", "b")
        r_sess2 = manager.store_member_memory("mem_1", "sess_2", "c")
        assert r_sess2.message_count == 1

    def test_different_members_have_separate_records(self, manager):
        manager.store_member_memory("mem_1", "sess_1", "a")
        r2 = manager.store_member_memory("mem_2", "sess_1", "b")
        assert r2.message_count == 1

    def test_rejects_empty_member_id(self, manager):
        with pytest.raises(ValueError, match="member_id"):
            manager.store_member_memory("", "sess_1", "ctx")

    def test_rejects_empty_session_id(self, manager):
        with pytest.raises(ValueError, match="session_id"):
            manager.store_member_memory("mem_1", "", "ctx")

    def test_rejects_whitespace_member_id(self, manager):
        with pytest.raises(ValueError, match="member_id"):
            manager.store_member_memory("   ", "sess_1", "ctx")

    def test_rejects_whitespace_session_id(self, manager):
        with pytest.raises(ValueError, match="session_id"):
            manager.store_member_memory("mem_1", "   ", "ctx")

    def test_updates_summary_on_subsequent_store(self, manager):
        manager.store_member_memory("mem_1", "sess_1", "first summary")
        r2 = manager.store_member_memory("mem_1", "sess_1", "updated summary")
        assert r2.summary == "updated summary"


class TestRetrieveMemberMemory:
    def test_returns_empty_list_when_no_records(self, manager):
        result = manager.retrieve_member_memory("mem_1")
        assert result == []

    def test_returns_stored_records(self, manager):
        manager.store_member_memory("mem_1", "sess_1", "ctx")
        result = manager.retrieve_member_memory("mem_1")
        assert len(result) == 1
        assert result[0].member_id == "mem_1"

    def test_returns_only_records_for_requested_member(self, manager):
        manager.store_member_memory("mem_1", "sess_1", "ctx1")
        manager.store_member_memory("mem_2", "sess_2", "ctx2")
        result = manager.retrieve_member_memory("mem_1")
        assert len(result) == 1
        assert all(r.member_id == "mem_1" for r in result)

    def test_returns_multiple_sessions_for_same_member(self, manager):
        manager.store_member_memory("mem_1", "sess_1", "ctx1")
        manager.store_member_memory("mem_1", "sess_2", "ctx2")
        result = manager.retrieve_member_memory("mem_1")
        assert len(result) == 2

    def test_rejects_empty_member_id(self, manager):
        with pytest.raises(ValueError, match="member_id"):
            manager.retrieve_member_memory("")

    def test_rejects_whitespace_member_id(self, manager):
        with pytest.raises(ValueError, match="member_id"):
            manager.retrieve_member_memory("   ")

    def test_does_not_return_family_records(self, manager):
        """Member retrieval never returns family memory records (tier isolation)."""
        manager.store_family_memory(
            family_id="fam_1",
            memory_key="health/allergy/peanut",
            category="health",
            content="allergy info",
        )
        manager.store_member_memory("mem_1", "sess_1", "member ctx")
        result = manager.retrieve_member_memory("mem_1")
        assert len(result) == 1
        assert all(isinstance(r, MemberMemoryRecord) for r in result)

# ── Availability / stateless mode ───────────────────────────────────────


class TestIsAvailable:
    def test_defaults_to_true(self, manager):
        assert manager.is_available is True

    def test_set_available_false(self, manager):
        manager.set_available(False)
        assert manager.is_available is False

    def test_set_available_true_again(self, manager):
        manager.set_available(False)
        manager.set_available(True)
        assert manager.is_available is True


# ── Safe retrieval wrappers ─────────────────────────────────────────────


class TestSafeRetrieveFamilyMemory:
    def test_returns_records_on_success(self, manager):
        manager.store_family_memory("fam_1", "health/a/b", "health", "data")
        result = manager.safe_retrieve_family_memory("fam_1")
        assert len(result) == 1
        assert result[0].family_id == "fam_1"

    def test_returns_empty_on_failure(self, manager):
        """Passing an empty family_id triggers ValueError; safe wrapper catches it."""
        result = manager.safe_retrieve_family_memory("")
        assert result == []

    def test_returns_empty_when_unavailable(self, manager):
        manager.store_family_memory("fam_1", "health/a/b", "health", "data")
        manager.set_available(False)
        result = manager.safe_retrieve_family_memory("fam_1")
        assert result == []

    def test_logs_warning_on_failure(self, manager, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            manager.safe_retrieve_family_memory("")
        assert "Failed to retrieve family memory" in caplog.text

    def test_logs_warning_when_unavailable(self, manager, caplog):
        import logging

        manager.set_available(False)
        with caplog.at_level(logging.WARNING):
            manager.safe_retrieve_family_memory("fam_1")
        assert "Memory service unavailable" in caplog.text


class TestSafeRetrieveMemberMemory:
    def test_returns_records_on_success(self, manager):
        manager.store_member_memory("mem_1", "sess_1", "ctx")
        result = manager.safe_retrieve_member_memory("mem_1")
        assert len(result) == 1
        assert result[0].member_id == "mem_1"

    def test_returns_empty_on_failure(self, manager):
        result = manager.safe_retrieve_member_memory("")
        assert result == []

    def test_returns_empty_when_unavailable(self, manager):
        manager.store_member_memory("mem_1", "sess_1", "ctx")
        manager.set_available(False)
        result = manager.safe_retrieve_member_memory("mem_1")
        assert result == []

    def test_logs_warning_on_failure(self, manager, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            manager.safe_retrieve_member_memory("")
        assert "Failed to retrieve member memory" in caplog.text

    def test_logs_warning_when_unavailable(self, manager, caplog):
        import logging

        manager.set_available(False)
        with caplog.at_level(logging.WARNING):
            manager.safe_retrieve_member_memory("mem_1")
        assert "Memory service unavailable" in caplog.text


# ── Safe store wrappers ─────────────────────────────────────────────────


class TestSafeStoreFamilyMemory:
    def test_stores_on_success(self, manager):
        result = manager.safe_store_family_memory(
            "fam_1", "health/a/b", "health", "data"
        )
        assert result is not None
        assert result.family_id == "fam_1"

    def test_returns_none_on_failure(self, manager):
        """Invalid category triggers ValueError; safe wrapper catches it."""
        result = manager.safe_store_family_memory(
            "fam_1", "bad/key/x", "INVALID", "data"
        )
        assert result is None

    def test_queues_failed_operation(self, manager):
        manager.safe_store_family_memory(
            "fam_1", "bad/key/x", "INVALID", "data"
        )
        queue = manager.get_retry_queue()
        assert len(queue) == 1
        assert queue[0]["operation"] == "store_family_memory"
        assert queue[0]["args"]["family_id"] == "fam_1"

    def test_returns_none_when_unavailable(self, manager):
        manager.set_available(False)
        result = manager.safe_store_family_memory(
            "fam_1", "health/a/b", "health", "data"
        )
        assert result is None

    def test_does_not_queue_when_unavailable(self, manager):
        """Stateless mode skips the operation entirely — nothing to retry."""
        manager.set_available(False)
        manager.safe_store_family_memory(
            "fam_1", "health/a/b", "health", "data"
        )
        assert manager.get_retry_queue() == []

    def test_logs_warning_on_failure(self, manager, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            manager.safe_store_family_memory(
                "fam_1", "bad/key/x", "INVALID", "data"
            )
        assert "Failed to store family memory" in caplog.text


class TestSafeStoreMemberMemory:
    def test_stores_on_success(self, manager):
        result = manager.safe_store_member_memory("mem_1", "sess_1", "ctx")
        assert result is not None
        assert result.member_id == "mem_1"

    def test_returns_none_on_failure(self, manager):
        result = manager.safe_store_member_memory("", "sess_1", "ctx")
        assert result is None

    def test_queues_failed_operation(self, manager):
        manager.safe_store_member_memory("", "sess_1", "ctx")
        queue = manager.get_retry_queue()
        assert len(queue) == 1
        assert queue[0]["operation"] == "store_member_memory"
        assert queue[0]["args"]["session_id"] == "sess_1"

    def test_returns_none_when_unavailable(self, manager):
        manager.set_available(False)
        result = manager.safe_store_member_memory("mem_1", "sess_1", "ctx")
        assert result is None

    def test_does_not_queue_when_unavailable(self, manager):
        manager.set_available(False)
        manager.safe_store_member_memory("mem_1", "sess_1", "ctx")
        assert manager.get_retry_queue() == []

    def test_logs_warning_on_failure(self, manager, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            manager.safe_store_member_memory("", "sess_1", "ctx")
        assert "Failed to store member memory" in caplog.text


# ── Retry queue management ──────────────────────────────────────────────


class TestRetryQueue:
    def test_empty_by_default(self, manager):
        assert manager.get_retry_queue() == []

    def test_get_retry_queue_returns_copy(self, manager):
        manager.safe_store_family_memory(
            "fam_1", "bad/key/x", "INVALID", "data"
        )
        q1 = manager.get_retry_queue()
        q1.clear()
        assert len(manager.get_retry_queue()) == 1

    def test_process_retry_queue_succeeds(self, manager):
        """Queue a valid operation that initially failed, then retry succeeds."""
        # Force a failure by making service unavailable, then store directly
        # to the retry queue with valid args
        manager._retry_queue.append(
            {
                "operation": "store_family_memory",
                "args": {
                    "family_id": "fam_1",
                    "memory_key": "health/allergy/peanut",
                    "category": "health",
                    "content": "allergy info",
                    "source_member_id": "",
                },
            }
        )
        remaining = manager.process_retry_queue()
        assert remaining == []
        assert manager.get_retry_queue() == []
        # Verify the record was actually stored
        records = manager.retrieve_family_memory("fam_1")
        assert len(records) == 1

    def test_process_retry_queue_keeps_failures(self, manager):
        """Operations that still fail remain in the queue."""
        manager._retry_queue.append(
            {
                "operation": "store_family_memory",
                "args": {
                    "family_id": "fam_1",
                    "memory_key": "bad/key/x",
                    "category": "INVALID",
                    "content": "data",
                    "source_member_id": "",
                },
            }
        )
        remaining = manager.process_retry_queue()
        assert len(remaining) == 1
        assert remaining[0]["operation"] == "store_family_memory"

    def test_process_retry_queue_member_memory(self, manager):
        manager._retry_queue.append(
            {
                "operation": "store_member_memory",
                "args": {
                    "member_id": "mem_1",
                    "session_id": "sess_1",
                    "content": "ctx",
                },
            }
        )
        remaining = manager.process_retry_queue()
        assert remaining == []
        records = manager.retrieve_member_memory("mem_1")
        assert len(records) == 1

    def test_process_retry_queue_mixed(self, manager):
        """Mix of successful and failing retries."""
        manager._retry_queue.append(
            {
                "operation": "store_family_memory",
                "args": {
                    "family_id": "fam_1",
                    "memory_key": "health/allergy/peanut",
                    "category": "health",
                    "content": "ok",
                    "source_member_id": "",
                },
            }
        )
        manager._retry_queue.append(
            {
                "operation": "store_family_memory",
                "args": {
                    "family_id": "fam_1",
                    "memory_key": "bad",
                    "category": "INVALID",
                    "content": "fail",
                    "source_member_id": "",
                },
            }
        )
        remaining = manager.process_retry_queue()
        assert len(remaining) == 1
        assert remaining[0]["args"]["category"] == "INVALID"

    def test_unknown_operation_stays_in_queue(self, manager):
        manager._retry_queue.append(
            {
                "operation": "unknown_op",
                "args": {},
            }
        )
        remaining = manager.process_retry_queue()
        assert len(remaining) == 1
        assert remaining[0]["operation"] == "unknown_op"
