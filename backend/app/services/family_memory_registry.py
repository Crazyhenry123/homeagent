"""FamilyMemoryStoreRegistry — maps each family to a dedicated AgentCore Memory store.

Provides cache-first lookup with DynamoDB fallback and on-demand provisioning
via the AgentCore CreateMemory API.  An in-memory cache with 5-minute TTL
avoids repeated DynamoDB lookups for active families.

Concurrent provisioning is handled via DynamoDB conditional writes
(``attribute_not_exists``).  If a race occurs the losing request re-reads
the table and adopts the winning store_id.

CreateMemory failures are retried with exponential backoff (max 3 attempts).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.models.agentcore import FamilyMemoryStoresItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CACHE_TTL_SECONDS = 300  # 5 minutes
_MAX_PROVISION_RETRIES = 3
_DEFAULT_EVENT_EXPIRY_DAYS = 365
_TABLE_NAME = "FamilyMemoryStores"


# ---------------------------------------------------------------------------
# Cache entry
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    """In-memory cache entry with timestamp for TTL enforcement."""

    store_id: str
    cached_at: float  # time.monotonic() value


# ---------------------------------------------------------------------------
# Store status result
# ---------------------------------------------------------------------------

@dataclass
class StoreStatus:
    """Result of a store status lookup."""

    store_id: str | None
    status: str  # "active" | "pending"


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class MemoryStoreProvisioningError(Exception):
    """Raised when store provisioning fails after all retries."""

    def __init__(self, family_id: str, cause: Exception | None = None) -> None:
        self.family_id = family_id
        self.cause = cause
        super().__init__(
            f"Failed to provision memory store for family {family_id}"
        )


# ---------------------------------------------------------------------------
# FamilyMemoryStoreRegistry
# ---------------------------------------------------------------------------


class FamilyMemoryStoreRegistry:
    """Maps each family_id to a dedicated AgentCore Memory store ID.

    Provisions new stores on-demand when a family is first encountered.
    Caches store IDs in-memory with a 5-minute TTL to avoid repeated
    DynamoDB lookups.

    Parameters
    ----------
    dynamodb_resource:
        A ``boto3.resource("dynamodb")`` instance.  Passed explicitly so
        the registry is testable with moto or DynamoDB Local.
    agentcore_client:
        A ``boto3.client("bedrock-agentcore")`` (or compatible) used to
        call ``create_memory``.  Passed explicitly for testability.
    table_name:
        Override the DynamoDB table name (default ``"FamilyMemoryStores"``).
    """

    def __init__(
        self,
        dynamodb_resource: Any,
        agentcore_client: Any,
        table_name: str = _TABLE_NAME,
    ) -> None:
        self._table = dynamodb_resource.Table(table_name)
        self._agentcore = agentcore_client
        self._cache: dict[str, _CacheEntry] = {}
        self._provision_locks: dict[str, threading.Lock] = {}
        self._provision_locks_guard = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_store_id(self, family_id: str) -> str:
        """Return the AgentCore Memory store ID for *family_id*.

        Resolution order:
        1. In-memory cache (if TTL has not expired)
        2. DynamoDB ``FamilyMemoryStores`` table
        3. On-demand provisioning via AgentCore ``CreateMemory``

        A per-family lock serialises the DynamoDB-check → provision path
        so that concurrent callers for the same family_id do not race
        past the cache and each trigger a separate ``CreateMemory`` call.

        Raises
        ------
        MemoryStoreProvisioningError
            If provisioning fails after all retries.
        """
        if not family_id or not family_id.strip():
            raise ValueError("family_id must be a non-empty string")

        # 1. Cache lookup (lock-free fast path)
        store_id = self._cache_get(family_id)
        if store_id is not None:
            return store_id

        # 2. Acquire per-family lock for DynamoDB check + provisioning
        lock = self._get_provision_lock(family_id)
        with lock:
            # Re-check cache — another thread may have populated it
            store_id = self._cache_get(family_id)
            if store_id is not None:
                return store_id

            # DynamoDB lookup
            entry = self._dynamo_get(family_id)
            if entry is not None and entry.get("status") == "active":
                sid = entry["store_id"]
                self._cache_set(family_id, sid)
                return sid

            # Provision new store
            return self.provision_family_store(family_id)

    def get_store_status(self, family_id: str) -> StoreStatus:
        """Return the store_id and status for *family_id*.

        Returns ``StoreStatus(store_id=..., status="active")`` when a
        store is ready, or ``StoreStatus(store_id=None, status="pending")``
        when no store has been provisioned yet.
        """
        if not family_id or not family_id.strip():
            raise ValueError("family_id must be a non-empty string")

        # Cache check
        store_id = self._cache_get(family_id)
        if store_id is not None:
            return StoreStatus(store_id=store_id, status="active")

        # DynamoDB check
        entry = self._dynamo_get(family_id)
        if entry is not None:
            status = entry.get("status", "pending")
            sid = entry.get("store_id")
            if status == "active" and sid:
                self._cache_set(family_id, sid)
                return StoreStatus(store_id=sid, status="active")
            # provisioning / migrating / decommissioned → treat as pending
            return StoreStatus(store_id=sid, status="pending")

        return StoreStatus(store_id=None, status="pending")

    def provision_family_store(self, family_id: str) -> str:
        """Provision a new AgentCore Memory store for *family_id*.

        1. Call ``CreateMemory`` with exponential-backoff retry (max 3).
        2. Register the mapping in DynamoDB with a conditional write
           (``attribute_not_exists(family_id)``) to prevent duplicates.
        3. Populate the in-memory cache.

        If a ``ConditionalCheckFailedException`` occurs (concurrent
        provisioning race), re-read the table and return the winning
        store_id.

        Raises
        ------
        MemoryStoreProvisioningError
            If all CreateMemory retries are exhausted.
        """
        if not family_id or not family_id.strip():
            raise ValueError("family_id must be a non-empty string")

        store_name = f"family_{family_id}"

        # Step 1: Create AgentCore Memory store with retry
        store_id = self._create_memory_with_retry(family_id, store_name)

        # Step 2: Register in DynamoDB (conditional write)
        now = datetime.now(timezone.utc).isoformat()
        item = FamilyMemoryStoresItem(
            family_id=family_id,
            store_id=store_id,
            store_name=store_name,
            created_at=now,
            updated_at=now,
            status="active",
            event_expiry_days=_DEFAULT_EVENT_EXPIRY_DAYS,
        )
        item.validate()

        try:
            self._table.put_item(
                Item={
                    "family_id": item.family_id,
                    "store_id": item.store_id,
                    "store_name": item.store_name,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                    "status": item.status,
                    "event_expiry_days": item.event_expiry_days,
                },
                ConditionExpression="attribute_not_exists(family_id)",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # Another request won the race — use their store_id
                logger.info(
                    "Concurrent provisioning detected for family %s; "
                    "re-reading winning store_id",
                    family_id,
                )
                entry = self._dynamo_get(family_id)
                if entry is not None and entry.get("store_id"):
                    winning_id = entry["store_id"]
                    self._cache_set(family_id, winning_id)
                    return winning_id
                # Shouldn't happen, but fall through to use our store_id
                logger.warning(
                    "Re-read after ConditionalCheckFailedException returned "
                    "no entry for family %s; using locally provisioned store_id",
                    family_id,
                )
            else:
                raise

        # Step 3: Populate cache
        self._cache_set(family_id, store_id)
        logger.info(
            "Provisioned memory store %s for family %s", store_id, family_id
        )
        return store_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cache_get(self, family_id: str) -> str | None:
        """Return cached store_id if present and TTL has not expired."""
        entry = self._cache.get(family_id)
        if entry is None:
            return None
        elapsed = time.monotonic() - entry.cached_at
        if elapsed >= _CACHE_TTL_SECONDS:
            del self._cache[family_id]
            return None
        return entry.store_id

    def _cache_set(self, family_id: str, store_id: str) -> None:
        """Insert or update a cache entry with the current timestamp."""
        self._cache[family_id] = _CacheEntry(
            store_id=store_id, cached_at=time.monotonic()
        )

    def _get_provision_lock(self, family_id: str) -> threading.Lock:
        """Return (or create) a per-family lock for provisioning."""
        with self._provision_locks_guard:
            if family_id not in self._provision_locks:
                self._provision_locks[family_id] = threading.Lock()
            return self._provision_locks[family_id]

    def _dynamo_get(self, family_id: str) -> dict[str, Any] | None:
        """Read a single item from the FamilyMemoryStores table."""
        try:
            response = self._table.get_item(Key={"family_id": family_id})
            return response.get("Item")
        except ClientError:
            logger.warning(
                "DynamoDB lookup failed for family %s", family_id, exc_info=True
            )
            return None

    def _create_memory_with_retry(
        self, family_id: str, store_name: str
    ) -> str:
        """Call AgentCore ``create_memory`` with exponential backoff.

        Returns the ``memory_id`` from the response on success.

        Raises
        ------
        MemoryStoreProvisioningError
            After *_MAX_PROVISION_RETRIES* consecutive failures.
        """
        last_error: Exception | None = None
        for attempt in range(1, _MAX_PROVISION_RETRIES + 1):
            try:
                response = self._agentcore.create_memory(
                    name=store_name,
                    description=f"Isolated family memory for {family_id}",
                    eventExpiryDuration=_DEFAULT_EVENT_EXPIRY_DAYS,
                )
                memory_id: str = response["memory"]["memoryId"]
                return memory_id
            except Exception as exc:
                last_error = exc
                wait = 2 ** (attempt - 1)  # 1s, 2s, 4s
                logger.warning(
                    "CreateMemory attempt %d/%d failed for family %s; "
                    "retrying in %ds",
                    attempt,
                    _MAX_PROVISION_RETRIES,
                    family_id,
                    wait,
                    exc_info=True,
                )
                time.sleep(wait)

        raise MemoryStoreProvisioningError(family_id, last_error)
