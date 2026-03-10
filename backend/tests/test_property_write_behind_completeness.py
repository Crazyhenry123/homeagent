"""Property-based tests for write-behind completeness.

Uses Hypothesis to verify Property 7: Write-Behind Completeness.

**Validates: Requirements 6.3, 6.6, 6.7**

Property 7: Write-Behind Completeness — for any family_id with buffered
operations, once the family's store becomes active and ``flush_buffer``
completes successfully, the buffer should be empty and all previously
buffered records should exist in the dedicated store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.memory_write_behind_buffer import MemoryWriteBehindBuffer

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_family_id = st.text(min_size=1, max_size=30).filter(lambda s: s.strip())
_store_id = st.text(min_size=1, max_size=30).filter(lambda s: s.strip())
_operation_type = st.sampled_from(["store_family", "store_member"])
_payload = st.fixed_dictionaries({"data": st.text(min_size=1, max_size=50)})

_operation_list = st.lists(
    st.tuples(_operation_type, _payload),
    min_size=1,
    max_size=20,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeStoreStatus:
    store_id: str | None
    status: str


class _FakeRegistry:
    """Registry that starts pending and can be switched to active."""

    def __init__(self) -> None:
        self._status: dict[str, _FakeStoreStatus] = {}

    def set_active(self, family_id: str, store_id: str) -> None:
        self._status[family_id] = _FakeStoreStatus(store_id=store_id, status="active")

    def set_pending(self, family_id: str) -> None:
        self._status[family_id] = _FakeStoreStatus(store_id=None, status="pending")

    def get_store_status(self, family_id: str) -> _FakeStoreStatus:
        return self._status.get(
            family_id, _FakeStoreStatus(store_id=None, status="pending")
        )


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class TestWriteBehindCompleteness:
    """Property 7: Write-Behind Completeness.

    **Validates: Requirements 6.3, 6.6, 6.7**
    """

    @given(
        family_id=_family_id,
        store_id=_store_id,
        ops=_operation_list,
    )
    @settings(max_examples=50, deadline=None)
    def test_flush_drains_buffer_and_stores_all_records(
        self,
        family_id: str,
        store_id: str,
        ops: list[tuple[str, dict[str, Any]]],
    ) -> None:
        """After flush, buffer is empty and all records exist in the store."""
        registry = _FakeRegistry()
        registry.set_pending(family_id)

        executed: list[tuple[str, str, dict[str, Any]]] = []

        def execute_fn(sid: str, op_type: str, payload: dict) -> None:
            executed.append((sid, op_type, payload))

        buf = MemoryWriteBehindBuffer(registry, execute_fn)

        # Buffer all operations while store is pending
        for op_type, payload in ops:
            buf.buffer_or_execute(family_id, op_type, payload)

        assert buf.has_pending(family_id), "Buffer should have pending ops"
        assert len(executed) == 0, "No ops should execute while pending"

        # Simulate store becoming active
        registry.set_active(family_id, store_id)
        result = buf.flush_buffer(family_id, store_id)

        # Buffer must be empty after flush
        assert not buf.has_pending(family_id), (
            "Buffer should be empty after successful flush"
        )

        # All records must have been flushed to the store
        assert result.flushed == len(ops), (
            f"Expected {len(ops)} flushed ops, got {result.flushed}"
        )
        assert result.failed == 0, f"Expected 0 failures, got {result.failed}"
        assert len(executed) == len(ops), (
            f"Expected {len(ops)} executed ops, got {len(executed)}"
        )

        # Verify each executed op used the correct store_id
        for sid, _, _ in executed:
            assert sid == store_id, (
                f"Operation executed against wrong store: {sid!r} != {store_id!r}"
            )
