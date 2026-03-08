"""AgentCore dual-tier memory configuration manager.

Provides configuration builders for family long-term memory and member
short-term memory stores. Each tier uses a distinct AgentCore Memory
store ID and scoped retrieval namespaces.

Family memory: scoped by family_id, namespaces for health and preferences.
Member memory: scoped by member_id, namespaces for context and session summaries.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.models.agentcore import (
    CONTENT_MAX_LENGTH,
    CombinedSessionManager,
    FamilyMemoryCategory,
    FamilyMemoryRecord,
    MemberMemoryRecord,
    MemoryConfig,
)

logger = logging.getLogger(__name__)


class AgentCoreMemoryManager:
    """Builds MemoryConfig objects for the dual-tier memory architecture.

    Uses distinct memory store IDs for family and member tiers to ensure
    strict isolation between long-term family knowledge and short-term
    member conversation context.
    """

    def __init__(self, family_memory_id: str, member_memory_id: str) -> None:
        if not family_memory_id or not family_memory_id.strip():
            raise ValueError("family_memory_id must be a non-empty string")
        if not member_memory_id or not member_memory_id.strip():
            raise ValueError("member_memory_id must be a non-empty string")
        if family_memory_id == member_memory_id:
            raise ValueError(
                "family_memory_id and member_memory_id must be distinct"
            )
        self._family_memory_id = family_memory_id
        self._member_memory_id = member_memory_id
        # In-memory backing store for family memory records, keyed by
        # (family_id, memory_key).  Will be replaced by AgentCore Memory
        # SDK integration in a later task.
        self._family_store: dict[tuple[str, str], FamilyMemoryRecord] = {}
        # In-memory backing store for member memory records, keyed by
        # (member_id, session_id).
        self._member_store: dict[tuple[str, str], MemberMemoryRecord] = {}
        # Retry queue for failed store operations (background retry)
        self._retry_queue: list[dict] = []
        # Availability flag — when False, safe_* methods return immediately
        # without attempting the operation (stateless mode)
        self._available: bool = True

    @property
    def family_memory_id(self) -> str:
        return self._family_memory_id

    @property
    def member_memory_id(self) -> str:
        return self._member_memory_id

    def get_family_memory_config(
        self, family_id: str, session_id: str
    ) -> MemoryConfig:
        """Build a MemoryConfig for the family long-term memory tier.

        Uses family_id as actor_id with retrieval namespaces:
        - /family/{actorId}/health
        - /family/{actorId}/preferences
        """
        if not family_id or not family_id.strip():
            raise ValueError("family_id must be a non-empty string")
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")

        return MemoryConfig(
            memory_id=self._family_memory_id,
            session_id=session_id,
            actor_id=family_id,
            retrieval_namespaces=[
                "/family/{actorId}/health",
                "/family/{actorId}/preferences",
            ],
        )

    def get_member_memory_config(
        self, member_id: str, session_id: str
    ) -> MemoryConfig:
        """Build a MemoryConfig for the member short-term memory tier.

        Uses member_id as actor_id with retrieval namespaces:
        - /member/{actorId}/context
        - /member/{actorId}/summaries/{sessionId}
        """
        if not member_id or not member_id.strip():
            raise ValueError("member_id must be a non-empty string")
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")

        return MemoryConfig(
            memory_id=self._member_memory_id,
            session_id=session_id,
            actor_id=member_id,
            retrieval_namespaces=[
                "/member/{actorId}/context",
                "/member/{actorId}/summaries/{sessionId}",
            ],
        )

    def create_combined_session_manager(
        self,
        family_id: str,
        member_id: str,
        session_id: str,
    ) -> CombinedSessionManager:
        """Build a CombinedSessionManager merging both memory tiers.

        Validates inputs, builds family and member memory configs, and
        returns a validated CombinedSessionManager.

        Note: The member_id-belongs-to-family_id verification and parallel
        memory retrieval are runtime concerns wired in later tasks.

        Raises:
            ValueError: If any input is empty or configs are invalid.
        """
        if not family_id or not family_id.strip():
            raise ValueError("family_id must be a non-empty string")
        if not member_id or not member_id.strip():
            raise ValueError("member_id must be a non-empty string")
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")

        family_config = self.get_family_memory_config(family_id, session_id)
        member_config = self.get_member_memory_config(member_id, session_id)

        combined = CombinedSessionManager(
            family_config=family_config,
            member_config=member_config,
            family_id=family_id,
            member_id=member_id,
            session_id=session_id,
        )
        combined.validate()
        return combined

    # ── Family long-term memory operations ──────────────────────────────

    def store_family_memory(
        self,
        family_id: str,
        memory_key: str,
        category: str,
        content: str,
        source_member_id: str = "",
    ) -> FamilyMemoryRecord:
        """Store a family long-term memory record (no TTL).

        Validates category against FamilyMemoryCategory, enforces the
        10 000-character content limit, and checks hierarchical memory_key
        format via FamilyMemoryRecord.validate().

        Args:
            family_id: The family this record belongs to.
            memory_key: Hierarchical key in ``{category}/{sub}/{id}`` format.
            category: One of health, preferences, context.
            content: The memory content (max 10 000 chars).
            source_member_id: Optional member who contributed the record.

        Returns:
            The persisted FamilyMemoryRecord.

        Raises:
            ValueError: On invalid inputs (bad category, key format, length).
        """
        now = datetime.now(timezone.utc).isoformat()
        record = FamilyMemoryRecord(
            family_id=family_id,
            memory_key=memory_key,
            category=category,
            content=content,
            source_member_id=source_member_id,
            agentcore_memory_id=self._family_memory_id,
            created_at=now,
            updated_at=now,
            ttl=None,
        )
        record.validate()

        key = (family_id, memory_key)
        existing = self._family_store.get(key)
        if existing is not None:
            # Update: preserve original created_at
            record.created_at = existing.created_at
        self._family_store[key] = record

        logger.info(
            "Stored family memory %s/%s (category=%s, len=%d)",
            family_id,
            memory_key,
            category,
            len(content),
        )
        return record

    def retrieve_family_memory(
        self,
        family_id: str,
    ) -> list[FamilyMemoryRecord]:
        """Retrieve all family memory records for a given family_id.

        Returns only records belonging to the specified family from the
        family memory store, ensuring tier isolation.

        Args:
            family_id: The family whose records to retrieve.

        Returns:
            List of FamilyMemoryRecord instances for the family.

        Raises:
            ValueError: If family_id is empty.
        """
        if not family_id or not family_id.strip():
            raise ValueError("family_id must be a non-empty string")

        records = [
            record
            for (fid, _), record in self._family_store.items()
            if fid == family_id
        ]
        logger.info(
            "Retrieved %d family memory records for %s",
            len(records),
            family_id,
        )
        return records

    # ── Member short-term memory operations ─────────────────────────────

    def store_member_memory(
        self,
        member_id: str,
        session_id: str,
        content: str,
    ) -> MemberMemoryRecord:
        """Store a member short-term memory record with 30-day TTL.

        Creates a new record or updates an existing one for the given
        (member_id, session_id) pair.  On each call the message_count is
        incremented (starts at 1 for new records).  The TTL is always
        computed as 30 days from the *original* creation timestamp.

        Args:
            member_id: The member this record belongs to.
            session_id: The session (conversation) this record belongs to.
            content: Summary / context text for the session.

        Returns:
            The persisted MemberMemoryRecord.

        Raises:
            ValueError: If member_id or session_id is empty.
        """
        if not member_id or not member_id.strip():
            raise ValueError("member_id must be a non-empty string")
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        key = (member_id, session_id)
        existing = self._member_store.get(key)

        if existing is not None:
            # Update existing record: preserve created_at, increment count
            created_at = existing.created_at
            message_count = existing.message_count + 1
            # TTL stays relative to original creation
            ttl_dt = datetime.fromisoformat(created_at) + timedelta(days=30)
            ttl_epoch = int(ttl_dt.timestamp())
        else:
            # New record
            created_at = now_iso
            message_count = 1
            ttl_epoch = int((now + timedelta(days=30)).timestamp())

        record = MemberMemoryRecord(
            member_id=member_id,
            session_id=session_id,
            agentcore_memory_id=self._member_memory_id,
            summary=content,
            message_count=message_count,
            created_at=created_at,
            updated_at=now_iso,
            ttl=ttl_epoch,
        )
        record.validate()
        self._member_store[key] = record

        logger.info(
            "Stored member memory %s/%s (msg_count=%d, ttl=%d)",
            member_id,
            session_id,
            message_count,
            ttl_epoch,
        )
        return record

    def retrieve_member_memory(
        self,
        member_id: str,
    ) -> list[MemberMemoryRecord]:
        """Retrieve all member memory records for a given member_id.

        Returns only records belonging to the specified member from the
        member memory store, ensuring tier isolation.  Records for other
        members are never returned.

        Args:
            member_id: The member whose records to retrieve.

        Returns:
            List of MemberMemoryRecord instances for the member.

        Raises:
            ValueError: If member_id is empty.
        """
        if not member_id or not member_id.strip():
            raise ValueError("member_id must be a non-empty string")

        records = [
            record
            for (mid, _), record in self._member_store.items()
            if mid == member_id
        ]
        logger.info(
            "Retrieved %d member memory records for %s",
            len(records),
            member_id,
        )
        return records

    # ── Availability / stateless mode ───────────────────────────────────

    @property
    def is_available(self) -> bool:
        """Return True if the memory service is available."""
        return self._available

    def set_available(self, available: bool) -> None:
        """Toggle memory service availability (for testing / stateless mode)."""
        self._available = available

    # ── Safe wrappers with error handling ───────────────────────────────

    def safe_retrieve_family_memory(
        self, family_id: str
    ) -> list[FamilyMemoryRecord]:
        """Retrieve family memory, returning empty list on failure.

        When the memory service is unavailable (_available is False),
        returns an empty list immediately without attempting the operation.
        On any exception, logs a warning and returns an empty list so the
        caller can proceed without memory context.
        """
        if not self._available:
            logger.warning(
                "Memory service unavailable; skipping family memory retrieval for %s",
                family_id,
            )
            return []
        try:
            return self.retrieve_family_memory(family_id)
        except Exception:
            logger.warning(
                "Failed to retrieve family memory for %s; proceeding without memory context",
                family_id,
                exc_info=True,
            )
            return []

    def safe_retrieve_member_memory(
        self, member_id: str
    ) -> list[MemberMemoryRecord]:
        """Retrieve member memory, returning empty list on failure.

        When the memory service is unavailable (_available is False),
        returns an empty list immediately without attempting the operation.
        On any exception, logs a warning and returns an empty list so the
        caller can proceed without memory context.
        """
        if not self._available:
            logger.warning(
                "Memory service unavailable; skipping member memory retrieval for %s",
                member_id,
            )
            return []
        try:
            return self.retrieve_member_memory(member_id)
        except Exception:
            logger.warning(
                "Failed to retrieve member memory for %s; proceeding without memory context",
                member_id,
                exc_info=True,
            )
            return []

    def safe_store_family_memory(
        self,
        family_id: str,
        memory_key: str,
        category: str,
        content: str,
        source_member_id: str = "",
    ) -> FamilyMemoryRecord | None:
        """Store family memory, queuing for retry on failure.

        When the memory service is unavailable (_available is False),
        returns None immediately without attempting the operation.
        On any exception, logs a warning, queues the failed operation
        to self._retry_queue, and returns None.
        """
        if not self._available:
            logger.warning(
                "Memory service unavailable; skipping family memory store for %s/%s",
                family_id,
                memory_key,
            )
            return None
        try:
            return self.store_family_memory(
                family_id, memory_key, category, content, source_member_id
            )
        except Exception:
            logger.warning(
                "Failed to store family memory for %s/%s; queuing for retry",
                family_id,
                memory_key,
                exc_info=True,
            )
            self._retry_queue.append(
                {
                    "operation": "store_family_memory",
                    "args": {
                        "family_id": family_id,
                        "memory_key": memory_key,
                        "category": category,
                        "content": content,
                        "source_member_id": source_member_id,
                    },
                }
            )
            return None

    def safe_store_member_memory(
        self,
        member_id: str,
        session_id: str,
        content: str,
    ) -> MemberMemoryRecord | None:
        """Store member memory, queuing for retry on failure.

        When the memory service is unavailable (_available is False),
        returns None immediately without attempting the operation.
        On any exception, logs a warning, queues the failed operation
        to self._retry_queue, and returns None.
        """
        if not self._available:
            logger.warning(
                "Memory service unavailable; skipping member memory store for %s/%s",
                member_id,
                session_id,
            )
            return None
        try:
            return self.store_member_memory(member_id, session_id, content)
        except Exception:
            logger.warning(
                "Failed to store member memory for %s/%s; queuing for retry",
                member_id,
                session_id,
                exc_info=True,
            )
            self._retry_queue.append(
                {
                    "operation": "store_member_memory",
                    "args": {
                        "member_id": member_id,
                        "session_id": session_id,
                        "content": content,
                    },
                }
            )
            return None

    # ── Retry queue management ──────────────────────────────────────────

    def get_retry_queue(self) -> list[dict]:
        """Return the current retry queue."""
        return list(self._retry_queue)

    def process_retry_queue(self) -> list[dict]:
        """Attempt to re-execute queued operations.

        Iterates over the retry queue and re-executes each operation.
        Successfully completed operations are removed from the queue.
        Failed operations remain for a future retry attempt.

        Returns:
            List of operations that still failed after this attempt.
        """
        remaining: list[dict] = []
        for item in self._retry_queue:
            op = item["operation"]
            args = item["args"]
            try:
                if op == "store_family_memory":
                    self.store_family_memory(**args)
                elif op == "store_member_memory":
                    self.store_member_memory(**args)
                else:
                    logger.warning("Unknown retry operation: %s", op)
                    remaining.append(item)
                    continue
            except Exception:
                logger.warning(
                    "Retry failed for %s; keeping in queue",
                    op,
                    exc_info=True,
                )
                remaining.append(item)
        self._retry_queue = remaining
        return remaining


