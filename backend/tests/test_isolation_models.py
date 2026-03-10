"""Unit tests for IsolatedContext and FamilyMemoryStoresItem data models."""

import pytest

from app.models.agentcore import FamilyMemoryStoresItem, IsolatedContext


# ---------------------------------------------------------------------------
# IsolatedContext tests
# ---------------------------------------------------------------------------


class TestIsolatedContext:
    """Tests for the IsolatedContext dataclass validation."""

    def test_valid_active_context(self) -> None:
        ctx = IsolatedContext(
            family_id="fam-1",
            member_id="mem-1",
            family_store_id="store-abc",
            is_verified=True,
            store_status="active",
            verified_at="2025-01-01T00:00:00Z",
        )
        ctx.validate()  # should not raise

    def test_valid_pending_context(self) -> None:
        ctx = IsolatedContext(
            family_id="fam-1",
            member_id="mem-1",
            family_store_id=None,
            is_verified=True,
            store_status="pending",
            verified_at="2025-01-01T00:00:00Z",
        )
        ctx.validate()

    def test_active_requires_store_id(self) -> None:
        ctx = IsolatedContext(
            family_id="fam-1",
            member_id="mem-1",
            family_store_id=None,
            is_verified=True,
            store_status="active",
            verified_at="2025-01-01T00:00:00Z",
        )
        with pytest.raises(ValueError, match="family_store_id must be non-empty"):
            ctx.validate()

    def test_active_rejects_blank_store_id(self) -> None:
        ctx = IsolatedContext(
            family_id="fam-1",
            member_id="mem-1",
            family_store_id="   ",
            is_verified=True,
            store_status="active",
            verified_at="2025-01-01T00:00:00Z",
        )
        with pytest.raises(ValueError, match="family_store_id must be non-empty"):
            ctx.validate()

    def test_verified_requires_family_id(self) -> None:
        ctx = IsolatedContext(
            family_id="",
            member_id="mem-1",
            family_store_id=None,
            is_verified=True,
            store_status="pending",
            verified_at="2025-01-01T00:00:00Z",
        )
        with pytest.raises(ValueError, match="family_id"):
            ctx.validate()

    def test_verified_requires_member_id(self) -> None:
        ctx = IsolatedContext(
            family_id="fam-1",
            member_id="",
            family_store_id=None,
            is_verified=True,
            store_status="pending",
            verified_at="2025-01-01T00:00:00Z",
        )
        with pytest.raises(ValueError, match="member_id"):
            ctx.validate()

    def test_invalid_store_status(self) -> None:
        ctx = IsolatedContext(
            family_id="fam-1",
            member_id="mem-1",
            family_store_id=None,
            is_verified=True,
            store_status="unknown",
            verified_at="2025-01-01T00:00:00Z",
        )
        with pytest.raises(ValueError, match="store_status must be one of"):
            ctx.validate()

    def test_unverified_allows_empty_ids(self) -> None:
        ctx = IsolatedContext(
            family_id="",
            member_id="",
            family_store_id=None,
            is_verified=False,
            store_status="pending",
            verified_at="",
        )
        ctx.validate()  # should not raise


# ---------------------------------------------------------------------------
# FamilyMemoryStoresItem tests
# ---------------------------------------------------------------------------


class TestFamilyMemoryStoresItem:
    """Tests for the FamilyMemoryStoresItem dataclass validation."""

    def _make_item(self, **overrides) -> FamilyMemoryStoresItem:
        defaults = dict(
            family_id="fam-1",
            store_id="store-abc",
            store_name="family_fam-1",
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
            status="active",
            event_expiry_days=365,
        )
        defaults.update(overrides)
        return FamilyMemoryStoresItem(**defaults)

    def test_valid_item(self) -> None:
        self._make_item().validate()

    def test_empty_family_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="family_id"):
            self._make_item(family_id="").validate()

    def test_empty_store_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="store_id"):
            self._make_item(store_id="").validate()

    @pytest.mark.parametrize("status", ["active", "migrating", "provisioning", "decommissioned"])
    def test_valid_statuses(self, status: str) -> None:
        self._make_item(status=status).validate()

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValueError, match="status must be one of"):
            self._make_item(status="deleted").validate()

    def test_zero_expiry_rejected(self) -> None:
        with pytest.raises(ValueError, match="event_expiry_days must be a positive"):
            self._make_item(event_expiry_days=0).validate()

    def test_negative_expiry_rejected(self) -> None:
        with pytest.raises(ValueError, match="event_expiry_days must be a positive"):
            self._make_item(event_expiry_days=-10).validate()

    def test_default_expiry_is_365(self) -> None:
        item = FamilyMemoryStoresItem(
            family_id="fam-1",
            store_id="store-abc",
            store_name="family_fam-1",
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
            status="active",
        )
        assert item.event_expiry_days == 365
