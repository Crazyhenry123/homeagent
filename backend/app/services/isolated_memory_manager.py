"""IsolatedMemoryManager — per-family memory configuration using IsolatedContext.

Replaces the global AgentCoreMemoryManager for isolated memory operations.
Instead of using global store IDs, it accepts a per-family store_id from
the IsolatedContext and builds MemoryConfig objects scoped to that specific
store.

Family memory tier: uses the family's dedicated store (context.family_store_id)
    with actor_id = context.family_id.
Member memory tier: continues using the shared member store with
    actor_id = context.member_id (no cross-family risk for member data).

Validates that family_store_id matches the expected store for the family_id
before any operation when a FamilyMemoryStoreRegistry is provided.
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.agentcore import (
    CombinedSessionManager,
    IsolatedContext,
    MemoryConfig,
)

logger = logging.getLogger(__name__)


class StoreValidationError(Exception):
    """Raised when family_store_id does not match the expected store for a family."""

    def __init__(self, family_id: str, expected: str | None, actual: str | None) -> None:
        self.family_id = family_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Store validation failed for family {family_id}: "
            f"expected store_id={expected!r}, got {actual!r}"
        )


class IsolatedMemoryManager:
    """Builds MemoryConfig objects scoped to per-family isolated stores.

    Wraps the existing :class:`AgentCoreMemoryManager` patterns but uses
    the ``family_store_id`` from an :class:`IsolatedContext` instead of a
    global family memory store ID.

    Parameters
    ----------
    member_memory_id:
        The shared member-tier AgentCore Memory store ID.  Member memory
        remains shared across families, scoped by ``member_id`` as
        ``actor_id``.
    registry:
        Optional :class:`FamilyMemoryStoreRegistry` used to verify that
        ``family_store_id`` matches the expected store for a given
        ``family_id``.  When ``None``, store validation is skipped.
    """

    def __init__(
        self,
        member_memory_id: str,
        registry: Any | None = None,
    ) -> None:
        if not member_memory_id or not member_memory_id.strip():
            raise ValueError("member_memory_id must be a non-empty string")
        self._member_memory_id = member_memory_id
        self._registry = registry
        self._available: bool = True

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def member_memory_id(self) -> str:
        return self._member_memory_id

    @property
    def is_available(self) -> bool:
        """Return True if the memory service is available."""
        return self._available

    def set_available(self, available: bool) -> None:
        """Toggle memory service availability (for testing / stateless mode)."""
        self._available = available

    # ------------------------------------------------------------------
    # Store validation
    # ------------------------------------------------------------------

    def validate_store(self, context: IsolatedContext) -> None:
        """Validate that family_store_id matches the expected store for the family.

        When a registry is available, queries it to verify the store_id.
        Always validates that family_store_id is non-empty for active contexts.

        Raises
        ------
        StoreValidationError
            If the store_id does not match the registry's expected value.
        ValueError
            If family_store_id is empty for an active context.
        """
        if context.store_status != "active":
            return

        if not context.family_store_id or not context.family_store_id.strip():
            raise ValueError(
                f"family_store_id must be non-empty for active context "
                f"(family_id={context.family_id})"
            )

        if self._registry is not None:
            expected_status = self._registry.get_store_status(context.family_id)
            if (
                expected_status.store_id is not None
                and expected_status.store_id != context.family_store_id
            ):
                raise StoreValidationError(
                    family_id=context.family_id,
                    expected=expected_status.store_id,
                    actual=context.family_store_id,
                )

    # ------------------------------------------------------------------
    # Config builders
    # ------------------------------------------------------------------

    def build_isolated_memory_config(
        self,
        context: IsolatedContext,
        session_id: str,
    ) -> CombinedSessionManager:
        """Build a CombinedSessionManager using per-family isolated store.

        Family tier: memory_id = context.family_store_id,
                     actor_id  = context.family_id
        Member tier: memory_id = shared member store,
                     actor_id  = context.member_id

        Validates the context and store_id before building configs.

        Parameters
        ----------
        context:
            The request-scoped IsolatedContext with verified family
            membership and resolved store information.
        session_id:
            The chat session identifier.

        Returns
        -------
        CombinedSessionManager
            Merged family and member memory tier configuration.

        Raises
        ------
        ValueError
            If context is not verified, store is not active, or
            session_id is empty.
        StoreValidationError
            If family_store_id does not match the registry.
        """
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        if not context.is_verified:
            raise ValueError("IsolatedContext must be verified before building memory config")
        if context.store_status != "active":
            raise ValueError(
                f"Cannot build memory config for non-active store "
                f"(status={context.store_status!r})"
            )

        # Validate store_id matches expectations
        self.validate_store(context)

        family_config = MemoryConfig(
            memory_id=context.family_store_id,  # type: ignore[arg-type]
            session_id=session_id,
            actor_id=context.family_id,
            retrieval_namespaces=[
                "/family/{actorId}/health",
                "/family/{actorId}/preferences",
            ],
        )

        member_config = MemoryConfig(
            memory_id=self._member_memory_id,
            session_id=session_id,
            actor_id=context.member_id,
            retrieval_namespaces=[
                "/member/{actorId}/context",
                "/member/{actorId}/summaries/{sessionId}",
            ],
        )

        combined = CombinedSessionManager(
            family_config=family_config,
            member_config=member_config,
            family_id=context.family_id,
            member_id=context.member_id,
            session_id=session_id,
        )
        combined.validate()
        return combined

    # ------------------------------------------------------------------
    # Safe wrappers with error handling
    # ------------------------------------------------------------------

    def safe_build_isolated_memory_config(
        self,
        context: IsolatedContext,
        session_id: str,
    ) -> CombinedSessionManager | None:
        """Build isolated memory config, returning None on failure.

        When the memory service is unavailable, returns None immediately.
        On any exception, logs a warning and returns None so the caller
        can proceed without memory context.
        """
        if not self._available:
            logger.warning(
                "Memory service unavailable; skipping isolated config build "
                "for family %s",
                context.family_id,
            )
            return None
        try:
            return self.build_isolated_memory_config(context, session_id)
        except Exception:
            logger.warning(
                "Failed to build isolated memory config for family %s; "
                "proceeding without memory context",
                context.family_id,
                exc_info=True,
            )
            return None

    def safe_validate_store(self, context: IsolatedContext) -> bool:
        """Validate store, returning False on failure.

        When the memory service is unavailable, returns False immediately.
        On any exception, logs a warning and returns False.
        """
        if not self._available:
            logger.warning(
                "Memory service unavailable; skipping store validation "
                "for family %s",
                context.family_id,
            )
            return False
        try:
            self.validate_store(context)
            return True
        except Exception:
            logger.warning(
                "Store validation failed for family %s; "
                "proceeding without memory context",
                context.family_id,
                exc_info=True,
            )
            return False
