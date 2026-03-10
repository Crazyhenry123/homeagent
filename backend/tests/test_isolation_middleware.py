"""Unit tests for IsolationMiddleware.

Validates the core behaviors:
- Membership verification (Req 1.2, 1.4, 1.5)
- Active store resolution with buffer flush (Req 8.4)
- Pending store with async provisioning (Req 8.2, 8.3)
- AccessDeniedError for non-members (Req 1.4)
- Input validation for empty family_id / member_id
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from app.models.agentcore import IsolatedContext
from app.services.family_memory_registry import StoreStatus
from app.services.isolation_middleware import (
    AccessDeniedError,
    IsolationMiddleware,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_middleware(
    membership_items: dict | None = None,
    store_status: StoreStatus | None = None,
    buffer: MagicMock | None = None,
) -> IsolationMiddleware:
    """Build an IsolationMiddleware with mocked dependencies."""
    # Mock DynamoDB resource + FamilyGroups table
    dynamo_resource = MagicMock()
    family_groups_table = MagicMock()

    def get_item_side_effect(Key):
        if membership_items is not None:
            key = (Key["family_id"], Key["member_id"])
            if key in membership_items:
                return {"Item": membership_items[key]}
        return {}

    family_groups_table.get_item.side_effect = get_item_side_effect
    dynamo_resource.Table.return_value = family_groups_table

    # Mock registry
    registry = MagicMock()
    if store_status is not None:
        registry.get_store_status.return_value = store_status

    mw = IsolationMiddleware(
        dynamodb_resource=dynamo_resource,
        registry=registry,
        buffer=buffer,
    )
    return mw


# ---------------------------------------------------------------------------
# Tests: AccessDeniedError for non-members (Req 1.4, 1.5)
# ---------------------------------------------------------------------------


class TestMembershipRejection:
    """Non-members are rejected with AccessDeniedError (HTTP 403)."""

    def test_non_member_raises_access_denied(self):
        mw = _make_middleware(membership_items={})
        with pytest.raises(AccessDeniedError) as exc_info:
            mw.validate_and_resolve("fam_1", "stranger")
        assert exc_info.value.status_code == 403
        assert exc_info.value.family_id == "fam_1"
        assert exc_info.value.member_id == "stranger"

    def test_access_denied_message(self):
        mw = _make_middleware(membership_items={})
        with pytest.raises(AccessDeniedError, match="Access denied"):
            mw.validate_and_resolve("fam_1", "stranger")

    def test_dynamo_error_treated_as_non_member(self):
        """If FamilyGroups lookup fails, treat as non-member (safe default)."""
        dynamo_resource = MagicMock()
        table = MagicMock()
        table.get_item.side_effect = Exception("DynamoDB unavailable")
        dynamo_resource.Table.return_value = table
        registry = MagicMock()

        mw = IsolationMiddleware(
            dynamodb_resource=dynamo_resource, registry=registry
        )
        with pytest.raises(AccessDeniedError):
            mw.validate_and_resolve("fam_1", "member_1")


# ---------------------------------------------------------------------------
# Tests: Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_empty_family_id_raises(self):
        mw = _make_middleware()
        with pytest.raises(ValueError, match="family_id"):
            mw.validate_and_resolve("", "member_1")

    def test_whitespace_family_id_raises(self):
        mw = _make_middleware()
        with pytest.raises(ValueError, match="family_id"):
            mw.validate_and_resolve("   ", "member_1")

    def test_empty_member_id_raises(self):
        mw = _make_middleware()
        with pytest.raises(ValueError, match="member_id"):
            mw.validate_and_resolve("fam_1", "")

    def test_whitespace_member_id_raises(self):
        mw = _make_middleware()
        with pytest.raises(ValueError, match="member_id"):
            mw.validate_and_resolve("fam_1", "   ")


# ---------------------------------------------------------------------------
# Tests: Active store resolution (Req 1.3, 8.4)
# ---------------------------------------------------------------------------


class TestActiveStoreResolution:
    def test_returns_active_context(self):
        mw = _make_middleware(
            membership_items={("fam_1", "mem_1"): {"family_id": "fam_1", "member_id": "mem_1"}},
            store_status=StoreStatus(store_id="store_abc", status="active"),
        )
        ctx = mw.validate_and_resolve("fam_1", "mem_1")

        assert isinstance(ctx, IsolatedContext)
        assert ctx.family_id == "fam_1"
        assert ctx.member_id == "mem_1"
        assert ctx.family_store_id == "store_abc"
        assert ctx.is_verified is True
        assert ctx.store_status == "active"
        assert ctx.verified_at  # non-empty ISO timestamp

    def test_active_store_flushes_pending_buffer(self):
        buf = MagicMock()
        buf.has_pending.return_value = True

        mw = _make_middleware(
            membership_items={("fam_1", "mem_1"): {"family_id": "fam_1", "member_id": "mem_1"}},
            store_status=StoreStatus(store_id="store_abc", status="active"),
            buffer=buf,
        )
        ctx = mw.validate_and_resolve("fam_1", "mem_1")

        buf.has_pending.assert_called_once_with("fam_1")
        buf.flush_buffer.assert_called_once_with("fam_1", "store_abc")
        assert ctx.store_status == "active"

    def test_active_store_no_flush_when_buffer_empty(self):
        buf = MagicMock()
        buf.has_pending.return_value = False

        mw = _make_middleware(
            membership_items={("fam_1", "mem_1"): {"family_id": "fam_1", "member_id": "mem_1"}},
            store_status=StoreStatus(store_id="store_abc", status="active"),
            buffer=buf,
        )
        mw.validate_and_resolve("fam_1", "mem_1")

        buf.has_pending.assert_called_once_with("fam_1")
        buf.flush_buffer.assert_not_called()

    def test_active_store_no_buffer_provided(self):
        """When no buffer is injected, skip flush logic entirely."""
        mw = _make_middleware(
            membership_items={("fam_1", "mem_1"): {"family_id": "fam_1", "member_id": "mem_1"}},
            store_status=StoreStatus(store_id="store_abc", status="active"),
            buffer=None,
        )
        ctx = mw.validate_and_resolve("fam_1", "mem_1")
        assert ctx.store_status == "active"
        assert ctx.family_store_id == "store_abc"


# ---------------------------------------------------------------------------
# Tests: Pending store with async provisioning (Req 8.1, 8.2, 8.3)
# ---------------------------------------------------------------------------


class TestPendingStoreResolution:
    def test_returns_pending_context(self):
        mw = _make_middleware(
            membership_items={("fam_1", "mem_1"): {"family_id": "fam_1", "member_id": "mem_1"}},
            store_status=StoreStatus(store_id=None, status="pending"),
        )
        ctx = mw.validate_and_resolve("fam_1", "mem_1")

        assert ctx.family_store_id is None
        assert ctx.store_status == "pending"
        assert ctx.is_verified is True

    def test_async_provisioning_is_triggered(self):
        mw = _make_middleware(
            membership_items={("fam_1", "mem_1"): {"family_id": "fam_1", "member_id": "mem_1"}},
            store_status=StoreStatus(store_id=None, status="pending"),
        )

        with patch.object(mw, "_start_async_provisioning") as mock_async:
            mw.validate_and_resolve("fam_1", "mem_1")
            mock_async.assert_called_once_with("fam_1")

    def test_async_provisioning_calls_registry(self):
        """The background thread calls registry.provision_family_store."""
        dynamo_resource = MagicMock()
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {"family_id": "fam_1", "member_id": "mem_1"}
        }
        dynamo_resource.Table.return_value = table

        registry = MagicMock()
        registry.get_store_status.return_value = StoreStatus(
            store_id=None, status="pending"
        )

        mw = IsolationMiddleware(
            dynamodb_resource=dynamo_resource, registry=registry
        )

        # Call the background method directly (not via thread) for determinism
        mw._provision_store_background("fam_1")
        registry.provision_family_store.assert_called_once_with("fam_1")

    def test_async_provisioning_failure_is_logged_not_raised(self):
        """Background provisioning errors are swallowed and logged."""
        dynamo_resource = MagicMock()
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {"family_id": "fam_1", "member_id": "mem_1"}
        }
        dynamo_resource.Table.return_value = table

        registry = MagicMock()
        registry.provision_family_store.side_effect = RuntimeError("boom")

        mw = IsolationMiddleware(
            dynamodb_resource=dynamo_resource, registry=registry
        )

        # Should not raise
        mw._provision_store_background("fam_1")
