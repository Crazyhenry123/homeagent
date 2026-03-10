"""IsolationMiddleware — verifies family membership and resolves per-family stores.

Intercepts every request that touches family memory.  Verifies the
requesting member belongs to the target family via the FamilyGroups
DynamoDB table, resolves the family's dedicated AgentCore Memory store
ID via :class:`FamilyMemoryStoreRegistry`, and returns an
:class:`IsolatedContext` for downstream use.

Handles three store states:
- **active**: store is ready — flushes any pending buffer, returns context.
- **pending** (provisioning or no entry): returns context with
  ``family_store_id=None`` and kicks off async provisioning.
- **non-member**: raises :class:`AccessDeniedError` (HTTP 403) and logs
  the attempt for security audit.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 8.1, 8.2, 8.3, 8.4
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Protocol

from app.models.agentcore import IsolatedContext
from app.services.family_memory_registry import FamilyMemoryStoreRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class AccessDeniedError(Exception):
    """Raised when a member is not part of the requested family.

    Maps to HTTP 403 — "Access denied: not a member of this family".
    """

    status_code = 403

    def __init__(self, family_id: str, member_id: str) -> None:
        self.family_id = family_id
        self.member_id = member_id
        super().__init__("Access denied: not a member of this family")


# ---------------------------------------------------------------------------
# Buffer protocol (for optional write-behind buffer integration)
# ---------------------------------------------------------------------------


class BufferProtocol(Protocol):
    """Minimal interface for the write-behind buffer.

    The actual :class:`MemoryWriteBehindBuffer` (task 7) will satisfy
    this protocol.  Accepting it here keeps the middleware decoupled.
    """

    def has_pending(self, family_id: str) -> bool: ...

    def flush_buffer(self, family_id: str, store_id: str) -> Any: ...


# ---------------------------------------------------------------------------
# IsolationMiddleware
# ---------------------------------------------------------------------------


class IsolationMiddleware:
    """Verifies family membership and resolves per-family memory stores.

    Parameters
    ----------
    dynamodb_resource:
        A ``boto3.resource("dynamodb")`` instance used to query the
        FamilyGroups table for membership verification.
    registry:
        A :class:`FamilyMemoryStoreRegistry` instance for store
        resolution and on-demand provisioning.
    buffer:
        An optional write-behind buffer implementing :class:`BufferProtocol`.
        When provided, the middleware flushes pending operations before
        returning an active context.
    family_groups_table_name:
        Override the DynamoDB table name (default ``"FamilyGroups"``).
    """

    def __init__(
        self,
        dynamodb_resource: Any,
        registry: FamilyMemoryStoreRegistry,
        buffer: BufferProtocol | None = None,
        family_groups_table_name: str = "FamilyGroups",
    ) -> None:
        self._family_groups_table = dynamodb_resource.Table(
            family_groups_table_name
        )
        self._registry = registry
        self._buffer = buffer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_and_resolve(
        self, family_id: str, member_id: str
    ) -> IsolatedContext:
        """Verify membership and resolve the per-family memory store.

        1. Query FamilyGroups to confirm *member_id* belongs to
           *family_id*.  Reject non-members with :class:`AccessDeniedError`.
        2. Resolve the store via :class:`FamilyMemoryStoreRegistry`.
        3. Return an :class:`IsolatedContext` appropriate for the store
           status (``"active"`` or ``"pending"``).

        For ``"pending"`` stores, asynchronous provisioning is kicked off
        and the context is returned immediately with
        ``family_store_id=None``.

        For ``"active"`` stores with a pending write-behind buffer, the
        buffer is flushed before the context is returned.

        Raises
        ------
        AccessDeniedError
            If *member_id* is not a member of *family_id*.
        ValueError
            If *family_id* or *member_id* is empty.
        """
        if not family_id or not family_id.strip():
            raise ValueError("family_id must be a non-empty string")
        if not member_id or not member_id.strip():
            raise ValueError("member_id must be a non-empty string")

        # Step 1: Verify family membership (Req 1.2)
        if not self._verify_membership(family_id, member_id):
            # Req 1.5 — log the attempt for security audit
            logger.warning(
                "Access denied: member_id=%s is not a member of "
                "family_id=%s at %s",
                member_id,
                family_id,
                datetime.now(timezone.utc).isoformat(),
            )
            raise AccessDeniedError(family_id, member_id)

        now = datetime.now(timezone.utc).isoformat()

        # Step 2: Resolve store status (Req 2.1–2.6, 8.1–8.4)
        store_status = self._registry.get_store_status(family_id)

        if store_status.status == "active" and store_status.store_id:
            # Active store — flush pending buffer if needed (Req 8.4)
            if self._buffer is not None and self._buffer.has_pending(family_id):
                self._buffer.flush_buffer(family_id, store_status.store_id)

            return IsolatedContext(
                family_id=family_id,
                member_id=member_id,
                family_store_id=store_status.store_id,
                is_verified=True,
                store_status="active",
                verified_at=now,
            )

        # Pending store — kick off async provisioning (Req 8.2, 8.3)
        self._start_async_provisioning(family_id)

        return IsolatedContext(
            family_id=family_id,
            member_id=member_id,
            family_store_id=None,
            is_verified=True,
            store_status="pending",
            verified_at=now,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _verify_membership(self, family_id: str, member_id: str) -> bool:
        """Check the FamilyGroups table for a (family_id, member_id) entry."""
        try:
            response = self._family_groups_table.get_item(
                Key={"family_id": family_id, "member_id": member_id}
            )
            return response.get("Item") is not None
        except Exception:
            logger.error(
                "Failed to verify membership for member_id=%s in "
                "family_id=%s",
                member_id,
                family_id,
                exc_info=True,
            )
            return False

    def _start_async_provisioning(self, family_id: str) -> None:
        """Kick off store provisioning in a background thread.

        Failures are logged but do not propagate — the next request for
        this family will retry provisioning.
        """
        thread = threading.Thread(
            target=self._provision_store_background,
            args=(family_id,),
            daemon=True,
        )
        thread.start()

    def _provision_store_background(self, family_id: str) -> None:
        """Background provisioning target — wraps registry call with
        error handling so the thread never raises unhandled exceptions."""
        try:
            self._registry.provision_family_store(family_id)
            logger.info(
                "Async provisioning completed for family_id=%s", family_id
            )
        except Exception:
            logger.error(
                "Async provisioning failed for family_id=%s; "
                "will retry on next request",
                family_id,
                exc_info=True,
            )
