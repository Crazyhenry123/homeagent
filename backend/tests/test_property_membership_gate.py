"""Property-based tests for the membership gate.

Uses Hypothesis to verify Property 2: Membership Gate.

**Validates: Requirements 1.2, 1.4**

Property 2: Membership Gate — for any family_id and member_id where the
member does not belong to the family, calling ``validate_and_resolve``
should raise an ``AccessDeniedError``.  Non-members can never obtain an
``IsolatedContext``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.isolation_middleware import (
    AccessDeniedError,
    IsolationMiddleware,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-empty, non-whitespace-only strings for family_id and member_id
_non_empty_str = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


class TestMembershipGate:
    """Property 2: Membership Gate.

    **Validates: Requirements 1.2, 1.4**
    """

    @given(family_id=_non_empty_str, member_id=_non_empty_str)
    @settings(max_examples=50, deadline=None)
    def test_non_member_always_raises_access_denied(
        self, family_id: str, member_id: str
    ) -> None:
        """For any family_id/member_id pair where the member does NOT
        belong to the family, ``validate_and_resolve`` must raise
        ``AccessDeniedError``.

        The FamilyGroups table mock returns no Item for every lookup,
        simulating that no member belongs to any family.
        """
        # Mock DynamoDB resource — FamilyGroups table returns empty (no Item)
        dynamo_resource = MagicMock()
        family_groups_table = MagicMock()
        family_groups_table.get_item.return_value = {}  # no "Item" key
        dynamo_resource.Table.return_value = family_groups_table

        # Mock registry (won't be reached — membership check fails first)
        registry = MagicMock()

        middleware = IsolationMiddleware(
            dynamodb_resource=dynamo_resource,
            registry=registry,
        )

        with pytest.raises(AccessDeniedError) as exc_info:
            middleware.validate_and_resolve(family_id, member_id)

        # Verify the error carries the correct identifiers
        assert exc_info.value.family_id == family_id
        assert exc_info.value.member_id == member_id
        assert exc_info.value.status_code == 403

        # Registry should never be consulted for non-members
        registry.get_store_status.assert_not_called()
