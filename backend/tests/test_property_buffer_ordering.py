"""Property-based tests for buffer ordering preservation.

Uses Hypothesis to verify Property 8: Buffer Ordering Preservation.

**Validates: Requirement 6.1**

Property 8: Buffer Ordering Preservation — for any family_id and any two
buffered operations op_i and op_j where op_i was queued before op_j,
op_i should be flushed to the store before op_j.  FIFO order is strictly
preserved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.memory_write_behind_buffer import MemoryWriteBehindBuffer

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_family_id = st.text(min_size=1, max_size=30).filter(lambda s: s.strip())
_store_id = st.text(min_size=1, max_size=30).filter(lambda s: s.strip())

# Each operation carries a unique sequence number in its payload so we can
# verify ordering after flush.
_indexed_ops = st.lists(
    st.integers(min_value=0, max_value=9999),
    min_size=2,
    max_size=30,
    unique=True,
).map(
    lambda indices: [
        ("store_family", {"seq": i, "data": f"record-{i}"})
        for i in indices
    ]
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeStoreStatus:
    store_id: str | None
    status: str


class _FakeRegistry:
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


class TestBufferOrderingPreservation:
    """Property 8: Buffer Ordering Preservation.

    **Validates: Requirement 6.1**
    """

    @given(
        family_id=_family_id,
        store_id=_store_id,
        ops=_indexed_ops,
    )
    @settings(max_examples=50, deadline=None)
    def test_flush_preserves_fifo_order(
        self,
        family_id: str,
        store_id: str,
        ops: list[tuple[str, dict[str, Any]]],
    ) -> None:
        """Operations are flushed in the exact order they were queued."""
        registry = _FakeRegistry()
        registry.set_pending(family_id)

        flush_order: list[int] = []

        def execute_fn(sid: str, op_type: str, payload: dict) -> None:
            flush_order.append(payload["seq"])

        buf = MemoryWriteBehindBuffer(registry, execute_fn)

        # Enqueue in order
        expected_order = []
        for op_type, payload in ops:
            buf.buffer_or_execute(family_id, op_type, payload)
            expected_order.append(payload["seq"])

        # Flush
        registry.set_active(family_id, store_id)
        result = buf.flush_buffer(family_id, store_id)

        assert result.flushed == len(ops)
        assert flush_order == expected_order, (
            f"FIFO order violated: expected {expected_order}, got {flush_order}"
        )
