"""Unit tests for IsolatedMemoryManager.

Tests cover:
- Config construction with per-family store IDs
- Store validation with and without registry
- Safe wrapper error handling
- Input validation
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from app.models.agentcore import CombinedSessionManager, IsolatedContext
from app.services.isolated_memory_manager import (
    IsolatedMemoryManager,
    StoreValidationError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MEMBER_STORE_ID = "mem-shared-member-store"
FAMILY_STORE_ID = "mem-family-abc-store"
FAMILY_ID = "family_abc"
MEMBER_ID = "member_123"
SESSION_ID = "sess_456"


def _make_active_context(
    family_id: str = FAMILY_ID,
    member_id: str = MEMBER_ID,
    family_store_id: str = FAMILY_STORE_ID,
) -> IsolatedContext:
    return IsolatedContext(
        family_id=family_id,
        member_id=member_id,
        family_store_id=family_store_id,
        is_verified=True,
        store_status="active",
        verified_at="2025-01-01T00:00:00+00:00",
    )


def _make_pending_context(
    family_id: str = FAMILY_ID,
    member_id: str = MEMBER_ID,
) -> IsolatedContext:
    return IsolatedContext(
        family_id=family_id,
        member_id=member_id,
        family_store_id=None,
        is_verified=True,
        store_status="pending",
        verified_at="2025-01-01T00:00:00+00:00",
    )


@pytest.fixture
def manager() -> IsolatedMemoryManager:
    return IsolatedMemoryManager(member_memory_id=MEMBER_STORE_ID)


@pytest.fixture
def mock_registry() -> MagicMock:
    registry = MagicMock()
    status = MagicMock()
    status.store_id = FAMILY_STORE_ID
    status.status = "active"
    registry.get_store_status.return_value = status
    return registry


@pytest.fixture
def manager_with_registry(mock_registry: MagicMock) -> IsolatedMemoryManager:
    return IsolatedMemoryManager(
        member_memory_id=MEMBER_STORE_ID,
        registry=mock_registry,
    )


# ---------------------------------------------------------------------------
# Construction tests
# ---------------------------------------------------------------------------


class TestIsolatedMemoryManagerInit:
    def test_rejects_empty_member_memory_id(self):
        with pytest.raises(ValueError, match="member_memory_id"):
            IsolatedMemoryManager(member_memory_id="")

    def test_rejects_whitespace_member_memory_id(self):
        with pytest.raises(ValueError, match="member_memory_id"):
            IsolatedMemoryManager(member_memory_id="   ")

    def test_stores_member_memory_id(self, manager: IsolatedMemoryManager):
        assert manager.member_memory_id == MEMBER_STORE_ID

    def test_default_available(self, manager: IsolatedMemoryManager):
        assert manager.is_available is True

    def test_set_available(self, manager: IsolatedMemoryManager):
        manager.set_available(False)
        assert manager.is_available is False


# ---------------------------------------------------------------------------
# build_isolated_memory_config tests
# ---------------------------------------------------------------------------


class TestBuildIsolatedMemoryConfig:
    def test_builds_family_config_with_isolated_store(self, manager: IsolatedMemoryManager):
        ctx = _make_active_context()
        result = manager.build_isolated_memory_config(ctx, SESSION_ID)

        assert isinstance(result, CombinedSessionManager)
        assert result.family_config.memory_id == FAMILY_STORE_ID
        assert result.family_config.actor_id == FAMILY_ID
        assert result.family_config.session_id == SESSION_ID

    def test_builds_member_config_with_shared_store(self, manager: IsolatedMemoryManager):
        ctx = _make_active_context()
        result = manager.build_isolated_memory_config(ctx, SESSION_ID)

        assert result.member_config.memory_id == MEMBER_STORE_ID
        assert result.member_config.actor_id == MEMBER_ID
        assert result.member_config.session_id == SESSION_ID

    def test_family_config_has_correct_namespaces(self, manager: IsolatedMemoryManager):
        ctx = _make_active_context()
        result = manager.build_isolated_memory_config(ctx, SESSION_ID)

        assert "/family/{actorId}/health" in result.family_config.retrieval_namespaces
        assert "/family/{actorId}/preferences" in result.family_config.retrieval_namespaces

    def test_member_config_has_correct_namespaces(self, manager: IsolatedMemoryManager):
        ctx = _make_active_context()
        result = manager.build_isolated_memory_config(ctx, SESSION_ID)

        assert "/member/{actorId}/context" in result.member_config.retrieval_namespaces
        assert "/member/{actorId}/summaries/{sessionId}" in result.member_config.retrieval_namespaces

    def test_sets_combined_metadata(self, manager: IsolatedMemoryManager):
        ctx = _make_active_context()
        result = manager.build_isolated_memory_config(ctx, SESSION_ID)

        assert result.family_id == FAMILY_ID
        assert result.member_id == MEMBER_ID
        assert result.session_id == SESSION_ID

    def test_rejects_empty_session_id(self, manager: IsolatedMemoryManager):
        ctx = _make_active_context()
        with pytest.raises(ValueError, match="session_id"):
            manager.build_isolated_memory_config(ctx, "")

    def test_rejects_unverified_context(self, manager: IsolatedMemoryManager):
        ctx = IsolatedContext(
            family_id=FAMILY_ID,
            member_id=MEMBER_ID,
            family_store_id=FAMILY_STORE_ID,
            is_verified=False,
            store_status="active",
            verified_at="2025-01-01T00:00:00+00:00",
        )
        with pytest.raises(ValueError, match="verified"):
            manager.build_isolated_memory_config(ctx, SESSION_ID)

    def test_rejects_pending_context(self, manager: IsolatedMemoryManager):
        ctx = _make_pending_context()
        with pytest.raises(ValueError, match="non-active"):
            manager.build_isolated_memory_config(ctx, SESSION_ID)

    def test_family_and_member_stores_are_distinct(self, manager: IsolatedMemoryManager):
        ctx = _make_active_context()
        result = manager.build_isolated_memory_config(ctx, SESSION_ID)
        assert result.family_config.memory_id != result.member_config.memory_id


# ---------------------------------------------------------------------------
# Store validation tests
# ---------------------------------------------------------------------------


class TestValidateStore:
    def test_skips_validation_for_pending_context(self, manager: IsolatedMemoryManager):
        ctx = _make_pending_context()
        # Should not raise
        manager.validate_store(ctx)

    def test_raises_on_empty_store_id_for_active(self, manager: IsolatedMemoryManager):
        ctx = IsolatedContext(
            family_id=FAMILY_ID,
            member_id=MEMBER_ID,
            family_store_id="",
            is_verified=True,
            store_status="active",
            verified_at="2025-01-01T00:00:00+00:00",
        )
        with pytest.raises(ValueError, match="family_store_id"):
            manager.validate_store(ctx)

    def test_passes_without_registry(self, manager: IsolatedMemoryManager):
        ctx = _make_active_context()
        # No registry → no cross-check, should pass
        manager.validate_store(ctx)

    def test_passes_with_matching_registry(
        self, manager_with_registry: IsolatedMemoryManager
    ):
        ctx = _make_active_context()
        # Registry returns matching store_id → should pass
        manager_with_registry.validate_store(ctx)

    def test_raises_on_mismatched_registry(
        self, mock_registry: MagicMock
    ):
        # Registry returns a different store_id
        status = MagicMock()
        status.store_id = "different-store-id"
        status.status = "active"
        mock_registry.get_store_status.return_value = status

        mgr = IsolatedMemoryManager(
            member_memory_id=MEMBER_STORE_ID,
            registry=mock_registry,
        )
        ctx = _make_active_context()
        with pytest.raises(StoreValidationError):
            mgr.validate_store(ctx)


# ---------------------------------------------------------------------------
# Safe wrapper tests
# ---------------------------------------------------------------------------


class TestSafeWrappers:
    def test_safe_build_returns_config_on_success(self, manager: IsolatedMemoryManager):
        ctx = _make_active_context()
        result = manager.safe_build_isolated_memory_config(ctx, SESSION_ID)
        assert result is not None
        assert result.family_config.memory_id == FAMILY_STORE_ID

    def test_safe_build_returns_none_when_unavailable(self, manager: IsolatedMemoryManager):
        manager.set_available(False)
        ctx = _make_active_context()
        result = manager.safe_build_isolated_memory_config(ctx, SESSION_ID)
        assert result is None

    def test_safe_build_returns_none_on_error(self, manager: IsolatedMemoryManager):
        ctx = _make_pending_context()  # Will fail: non-active store
        result = manager.safe_build_isolated_memory_config(ctx, SESSION_ID)
        assert result is None

    def test_safe_validate_returns_true_on_success(self, manager: IsolatedMemoryManager):
        ctx = _make_active_context()
        assert manager.safe_validate_store(ctx) is True

    def test_safe_validate_returns_false_when_unavailable(self, manager: IsolatedMemoryManager):
        manager.set_available(False)
        ctx = _make_active_context()
        assert manager.safe_validate_store(ctx) is False

    def test_safe_validate_returns_false_on_mismatch(self, mock_registry: MagicMock):
        status = MagicMock()
        status.store_id = "wrong-store"
        status.status = "active"
        mock_registry.get_store_status.return_value = status

        mgr = IsolatedMemoryManager(
            member_memory_id=MEMBER_STORE_ID,
            registry=mock_registry,
        )
        ctx = _make_active_context()
        assert mgr.safe_validate_store(ctx) is False
