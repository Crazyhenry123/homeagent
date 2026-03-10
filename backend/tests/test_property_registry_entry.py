"""Property-based tests for FamilyMemoryStoresItem registry entry validation.

Uses Hypothesis to verify Property 12: Registry Entry Validation.

**Validates: Requirements 4.3, 4.4**

Property 12: Registry Entry Validation — for any FamilyMemoryStoresItem
written to the table, family_id and store_id must be non-empty strings,
and status must be one of "active", "migrating", "provisioning", or
"decommissioned".
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.agentcore import FamilyMemoryStoresItem

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-empty, non-whitespace-only strings for identifiers
_nonempty_str = st.text(min_size=1).filter(lambda s: s.strip())

_VALID_STATUSES = ["active", "migrating", "provisioning", "decommissioned"]

_valid_status = st.sampled_from(_VALID_STATUSES)

_positive_int = st.integers(min_value=1, max_value=10_000)

# ISO 8601-ish timestamp strings (content doesn't matter for validation)
_timestamp = st.text(min_size=1, max_size=30)

# Strategy for a fully valid FamilyMemoryStoresItem
_valid_item = st.builds(
    FamilyMemoryStoresItem,
    family_id=_nonempty_str,
    store_id=_nonempty_str,
    store_name=_nonempty_str,
    created_at=_timestamp,
    updated_at=_timestamp,
    status=_valid_status,
    event_expiry_days=_positive_int,
)


class TestRegistryEntryValidation:
    """Property 12: Registry Entry Validation.

    **Validates: Requirements 4.3, 4.4**
    """

    @given(item=_valid_item)
    @settings(max_examples=50)
    def test_valid_item_has_nonempty_family_id(
        self, item: FamilyMemoryStoresItem
    ) -> None:
        """family_id is always a non-empty string for valid items."""
        item.validate()
        assert isinstance(item.family_id, str)
        assert item.family_id.strip() != ""

    @given(item=_valid_item)
    @settings(max_examples=50)
    def test_valid_item_has_nonempty_store_id(
        self, item: FamilyMemoryStoresItem
    ) -> None:
        """store_id is always a non-empty string for valid items."""
        item.validate()
        assert isinstance(item.store_id, str)
        assert item.store_id.strip() != ""

    @given(item=_valid_item)
    @settings(max_examples=50)
    def test_valid_item_has_allowed_status(
        self, item: FamilyMemoryStoresItem
    ) -> None:
        """status is always in the allowed set for valid items."""
        item.validate()
        assert item.status in {"active", "migrating", "provisioning", "decommissioned"}

    @given(item=_valid_item)
    @settings(max_examples=50)
    def test_valid_item_passes_full_validation(
        self, item: FamilyMemoryStoresItem
    ) -> None:
        """A randomly generated valid item always passes validate() without error."""
        item.validate()  # should not raise
