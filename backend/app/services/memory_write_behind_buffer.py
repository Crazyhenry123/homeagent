"""MemoryWriteBehindBuffer — server-side write-behind cache for pending stores.

Queues memory operations in-memory when a family's AgentCore Memory store
is not yet provisioned and flushes them in FIFO order once the store
becomes active.  This ensures chat is never blocked by store provisioning.

Key behaviours:
- ``buffer_or_execute``: routes operations through the buffer or directly
  to the store depending on the store status.
- ``flush_buffer``: drains all buffered operations to the store in FIFO
  order, retrying failures up to 3 times before discarding.
- ``has_pending`` / ``get_buffered_records``: allow callers to query
  buffered state while the store is pending.
- Max 100 operations per family buffer; oldest evicted on overflow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

MAX_BUFFER_SIZE = 100
MAX_FLUSH_ATTEMPTS = 3


@dataclass
class BufferedMemoryOperation:
    """A single queued memory operation."""

    operation_type: str
    family_id: str
    payload: dict[str, Any]
    queued_at: str
    attempt_count: int = 0


@dataclass
class BufferState:
    """Per-family buffer state."""

    family_id: str
    status: str  # "buffering" | "flushing" | "flushed"
    operations: list[BufferedMemoryOperation] = field(default_factory=list)
    store_id: str | None = None
    created_at: str = ""
    flushed_at: str | None = None


@dataclass
class FlushResult:
    """Outcome of a flush operation."""

    flushed: int = 0
    failed: int = 0


@dataclass
class BufferAcknowledgement:
    """Returned when an operation is queued rather than executed."""

    queued: bool = True
    position: int = 0


class MemoryWriteBehindBuffer:
    """In-memory write-behind buffer for pending family stores.

    Parameters
    ----------
    registry:
        A :class:`FamilyMemoryStoreRegistry` (or compatible object) that
        exposes ``get_store_status(family_id)`` returning an object with
        ``status`` (``"active"`` | ``"pending"``) and ``store_id``.
    execute_fn:
        Callable ``(store_id, operation_type, payload) -> Any`` that
        performs the actual memory operation against AgentCore.
    """

    def __init__(
        self,
        registry: Any,
        execute_fn: Callable[..., Any],
    ) -> None:
        self._registry = registry
        self._execute = execute_fn
        self._buffers: dict[str, BufferState] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def buffer_or_execute(
        self,
        family_id: str,
        operation: str,
        payload: dict[str, Any],
    ) -> Any:
        """Route an operation through the buffer or execute directly.

        If the family's store is active, any pending buffer is flushed
        first and then the operation is executed directly.  If the store
        is pending, the operation is enqueued.

        For ``"retrieve"`` operations while pending, buffered records
        matching ``payload.get("filters")`` are returned.
        """
        if not family_id or not family_id.strip():
            raise ValueError("family_id must be a non-empty string")

        store_status = self._registry.get_store_status(family_id)

        if store_status.status == "active" and store_status.store_id:
            # Store ready — flush pending ops first, then execute directly
            if self.has_pending(family_id):
                self.flush_buffer(family_id, store_status.store_id)
            return self._execute(store_status.store_id, operation, payload)

        # Store pending — buffer the operation
        now = datetime.now(timezone.utc).isoformat()
        buffered_op = BufferedMemoryOperation(
            operation_type=operation,
            family_id=family_id,
            payload=payload,
            queued_at=now,
        )
        self._enqueue(family_id, buffered_op)

        # For retrieves, return whatever is in the buffer
        if operation == "retrieve":
            return self.get_buffered_records(family_id, payload.get("filters"))

        return BufferAcknowledgement(
            queued=True,
            position=len(self._get_or_create_state(family_id).operations),
        )

    def flush_buffer(self, family_id: str, store_id: str) -> FlushResult:
        """Flush all buffered operations for *family_id* to *store_id*.

        Operations are flushed in strict FIFO order.  Failed operations
        are retried up to ``MAX_FLUSH_ATTEMPTS`` times; after that they
        are logged and discarded.

        Returns a :class:`FlushResult` with counts of flushed and failed
        operations.  Cleans up buffer state when all operations are
        drained.
        """
        if not family_id or not family_id.strip():
            raise ValueError("family_id must be a non-empty string")
        if not store_id or not store_id.strip():
            raise ValueError("store_id must be a non-empty string")

        state = self._buffers.get(family_id)
        if state is None or state.status == "flushed" or not state.operations:
            return FlushResult(flushed=0, failed=0)

        state.status = "flushing"
        flushed = 0
        permanently_failed: list[BufferedMemoryOperation] = []
        still_pending: list[BufferedMemoryOperation] = []

        for op in state.operations:
            try:
                self._execute(store_id, op.operation_type, op.payload)
                flushed += 1
            except Exception:
                op.attempt_count += 1
                if op.attempt_count >= MAX_FLUSH_ATTEMPTS:
                    logger.error(
                        "Permanent flush failure for family %s: op=%s payload=%s",
                        family_id,
                        op.operation_type,
                        op.payload,
                    )
                    permanently_failed.append(op)
                else:
                    still_pending.append(op)

        failed = len(permanently_failed) + len(still_pending)

        if still_pending:
            # Keep retryable ops for next attempt
            state.operations = still_pending
            state.status = "buffering"
        else:
            # All ops either flushed or permanently failed — clean up
            now = datetime.now(timezone.utc).isoformat()
            state.operations = []
            state.status = "flushed"
            state.flushed_at = now
            state.store_id = store_id
            del self._buffers[family_id]

        return FlushResult(flushed=flushed, failed=failed)

    def has_pending(self, family_id: str) -> bool:
        """Return True if *family_id* has buffered operations."""
        state = self._buffers.get(family_id)
        return state is not None and len(state.operations) > 0

    def get_buffered_records(
        self,
        family_id: str,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return buffered payloads for *family_id*, optionally filtered.

        When *filters* is ``None`` or empty, all buffered payloads are
        returned.  Otherwise each filter key/value must match the
        corresponding key in the operation payload.
        """
        state = self._buffers.get(family_id)
        if state is None:
            return []

        results: list[dict[str, Any]] = []
        for op in state.operations:
            if filters:
                if all(op.payload.get(k) == v for k, v in filters.items()):
                    results.append(op.payload)
            else:
                results.append(op.payload)
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_or_create_state(self, family_id: str) -> BufferState:
        if family_id not in self._buffers:
            self._buffers[family_id] = BufferState(
                family_id=family_id,
                status="buffering",
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        return self._buffers[family_id]

    def _enqueue(
        self,
        family_id: str,
        op: BufferedMemoryOperation,
    ) -> None:
        state = self._get_or_create_state(family_id)

        if len(state.operations) >= MAX_BUFFER_SIZE:
            evicted = state.operations.pop(0)
            logger.warning(
                "Buffer overflow for family %s: evicting oldest op=%s "
                "payload=%s (buffer at %d)",
                family_id,
                evicted.operation_type,
                evicted.payload,
                MAX_BUFFER_SIZE,
            )

        state.operations.append(op)
