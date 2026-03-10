"""Property-based tests for pending context chat availability.

Uses Hypothesis to verify Property 9: Pending Context Chat Availability.

**Validates: Requirements 8.1, 8.4**

Property 9: Pending Context Chat Availability — for any verified family
member, ``validate_and_resolve`` should return an ``IsolatedContext``
regardless of whether the store_status is "active" or "pending".  Chat
is never blocked by store provisioning.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models.agentcore import IsolatedContext
from app.services.family_memory_registry import StoreStatus
from app.services.isolation_middleware import IsolationMiddleware

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-empty, non-whitespace-only strings for family_id and member_id
_non_empty_str = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())

# Store status: either "active" (with a store_id) or "pending" (store_id=None)
_store_status = st.one_of(
    st.tuples(
        _non_empty_str,
        st.just("active"),
    ).map(lambda t: StoreStatus(store_id=t[0], status=t[1])),
    st.just(StoreStatus(store_id=None, status="pending")),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_middleware(
    family_id: str,
    member_id: str,
    store_status: StoreStatus,
) -> IsolationMiddleware:
    """Build an IsolationMiddleware with mocked dependencies.

    The FamilyGroups table mock returns a valid Item for the given
    (family_id, member_id) pair, simulating valid membership.
    The registry mock returns the provided StoreStatus.
    """
    dynamo_resource = MagicMock()
    family_groups_table = MagicMock()
    family_groups_table.get_item.return_value = {
        "Item": {"family_id": family_id, "member_id": member_id}
    }
    dynamo_resource.Table.return_value = family_groups_table

    registry = MagicMock()
    registry.get_store_status.return_value = store_status

    return IsolationMiddleware(
        dynamodb_resource=dynamo_resource,
        registry=registry,
    )


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


class TestPendingContextChatAvailability:
    """Property 9: Pending Context Chat Availability.

    **Validates: Requirements 8.1, 8.4**
    """

    @given(
        family_id=_non_empty_str,
        member_id=_non_empty_str,
        store_status=_store_status,
    )
    @settings(max_examples=50, deadline=None)
    def test_verified_member_always_gets_context(
        self, family_id: str, member_id: str, store_status: StoreStatus
    ) -> None:
        """For any verified family member, ``validate_and_resolve`` returns
        an ``IsolatedContext`` regardless of store status — never raises.

        Both "active" and "pending" store states must produce a valid
        context so that chat is never blocked by store provisioning.
        """
        middleware = _build_middleware(family_id, member_id, store_status)

        # Patch _start_async_provisioning to avoid spawning real threads
        with patch.object(middleware, "_start_async_provisioning"):
            ctx = middleware.validate_and_resolve(family_id, member_id)

        # An IsolatedContext is always returned
        assert isinstance(ctx, IsolatedContext)
        assert ctx.family_id == family_id
        assert ctx.member_id == member_id
        assert ctx.is_verified is True
        assert ctx.verified_at  # non-empty ISO timestamp

        # Store status in context matches the registry status
        if store_status.status == "active":
            assert ctx.store_status == "active"
            assert ctx.family_store_id == store_status.store_id
        else:
            assert ctx.store_status == "pending"
            assert ctx.family_store_id is None
