# Multi-Family Memory Isolation — Implementation Guide

## Problem

HomeAgent previously used two global AgentCore Memory stores shared across all families, relying on application-level filtering by `family_id` for isolation. A bug in filtering logic could leak one family's private memories (health records, preferences, conversation context) to another. This is a data privacy risk that cannot be mitigated by testing alone.

## Solution

Infrastructure-enforced memory isolation: each family gets a dedicated AgentCore Memory store. Even if application-level filtering fails, the underlying store physically cannot return another family's data.

## Architecture

```
Request → IsolationMiddleware → FamilyMemoryStoreRegistry → IsolatedMemoryManager → AgentCore Runtime
              │                         │                          │
              │ verify membership       │ resolve/provision        │ build per-family MemoryConfig
              │ (FamilyGroups table)    │ (FamilyMemoryStores)     │ (family_store_id, not global)
              │                         │                          │
              ▼                         ▼                          ▼
         AccessDeniedError         DynamoDB + Cache          CombinedSessionManager
         (HTTP 403)                + AgentCore CreateMemory   with isolated store_id
```

When a family's store is still being provisioned, the `MemoryWriteBehindBuffer` queues operations in-memory and flushes them once the store becomes active. Chat is never blocked.

## Components

### 1. Data Models (`backend/app/models/agentcore.py`)

Two dataclasses were added:

`IsolatedContext` — request-scoped context carrying verified membership and store info:
- `family_id`, `member_id`, `family_store_id` (None when pending), `is_verified`, `store_status` ("active" | "pending"), `verified_at`

`FamilyMemoryStoresItem` — persistent registry entry in DynamoDB:
- `family_id` (PK), `store_id`, `store_name`, `created_at`, `updated_at`, `status` ("active" | "migrating" | "provisioning" | "decommissioned"), `event_expiry_days`

Both include `validate()` methods enforcing field constraints.

### 2. FamilyMemoryStoreRegistry (`backend/app/services/family_memory_registry.py`)

Maps each `family_id` to a dedicated AgentCore Memory store ID. Resolution order:

1. In-memory cache (5-minute TTL)
2. DynamoDB `FamilyMemoryStores` table
3. On-demand provisioning via AgentCore `CreateMemory` API

Key design decisions:
- Per-family provisioning lock (`threading.Lock`) prevents concurrent callers from each triggering separate `CreateMemory` calls for the same family. Different families resolve concurrently.
- DynamoDB conditional write (`attribute_not_exists(family_id)`) as a second line of defense against duplicate stores. On `ConditionalCheckFailedException`, the losing request re-reads and adopts the winning store_id.
- Exponential backoff retry (max 3 attempts) for `CreateMemory` failures.

### 3. IsolationMiddleware (`backend/app/services/isolation_middleware.py`)

Intercepts every request touching family memory:

1. Verifies `member_id` belongs to `family_id` via the `FamilyGroups` DynamoDB table.
2. Rejects non-members with `AccessDeniedError` (HTTP 403) and logs the attempt.
3. Resolves the store via `FamilyMemoryStoreRegistry.get_store_status()`.
4. For active stores with pending buffer: flushes before returning context.
5. For pending stores: kicks off async provisioning in a daemon thread and returns context with `family_store_id=None`.

### 4. IsolatedMemoryManager (`backend/app/services/isolated_memory_manager.py`)

Builds `CombinedSessionManager` using per-family store IDs instead of global ones:

- Family tier: `memory_id = context.family_store_id`, `actor_id = context.family_id`
- Member tier: unchanged — shared store with `actor_id = context.member_id` (no cross-family risk)

Validates that `family_store_id` matches the registry before any operation. Provides `safe_*` wrappers that return `None`/`False` on failure so chat can proceed without memory context.

### 5. MemoryWriteBehindBuffer (`backend/app/services/memory_write_behind_buffer.py`)

Server-side write-behind cache for the registration-to-first-chat path:

- `buffer_or_execute()`: if store active, flush pending then execute directly; if pending, enqueue.
- `flush_buffer()`: drains in strict FIFO order, retries up to 3 times, discards permanently failed ops with error log.
- Max 100 operations per family; oldest evicted on overflow with warning log containing full payload for manual recovery.
- Buffer state cleaned up after successful full flush.

### 6. MigrationOrchestrator (`backend/scripts/migrate_memory_stores.py`)

One-time migration tool:

```bash
python -m backend.scripts.migrate_memory_stores \
  --shared-store-id <STORE_ID> \
  --region us-east-1 \
  --dry-run
```

- Enumerates distinct `family_id` values from the shared store.
- Provisions per-family stores, copies records, verifies counts.
- Skips families that already have active dedicated stores.
- Marks stores as "migrating" on record count mismatch.
- Produces a `MigrationReport` with migrated/failed/skipped counts.
- Supports `--dry-run` mode.

### 7. CDK Infrastructure (`infra/stacks/data_stack.py`, `infra/stacks/security_stack.py`)

- `FamilyMemoryStores` DynamoDB table: PK = `family_id`, on-demand billing, point-in-time recovery enabled, RETAIN removal policy.
- IAM: ECS task role gets `grant_read_write_data` on all tables (including `FamilyMemoryStores`) and `bedrock-agentcore:CreateMemory` / `bedrock-agentcore:GetMemory` permissions.

### 8. Chat Route Integration (`backend/app/routes/chat.py`)

The `_get_agentcore_chat_stream` function orchestrates the isolation flow:

```
if family_id:
    registry = FamilyMemoryStoreRegistry(dynamodb, agentcore_client)
    buffer = MemoryWriteBehindBuffer(registry, execute_fn)
    middleware = IsolationMiddleware(dynamodb, registry, buffer)
    context = middleware.validate_and_resolve(family_id, user_id)  # may raise AccessDeniedError

    if context.store_status == "active":
        iso_manager = IsolatedMemoryManager(member_memory_id, registry)
        isolated_memory_config = iso_manager.safe_build_isolated_memory_config(context, conversation_id)
    else:
        isolated_memory_config = None  # pending — chat proceeds without family memory

    stream_agent_chat_v2(..., isolated_memory_config=isolated_memory_config)
else:
    stream_agent_chat_v2(...)  # global fallback
```

`AccessDeniedError` is caught at the route level and returned as HTTP 403.

## Correctness Properties & Test Suite

All properties are validated with Hypothesis property-based tests (`max_examples=50`).

| # | Property | What it proves | Test file |
|---|----------|---------------|-----------|
| 1 | Store Isolation Guarantee | Distinct families always get distinct store_ids | `test_property_store_isolation.py` |
| 2 | Membership Gate | Non-members always get AccessDeniedError | `test_property_pending_context.py` (via middleware) |
| 3 | Store-Data Affinity | Retrieved records originate from the family's dedicated store | `test_property_store_data_affinity.py` |
| 4 | Idempotent Provisioning | Repeated/concurrent `get_store_id` returns same value | `test_property_idempotent_provisioning.py` |
| 5 | Migration Completeness | Migrated record count matches source per family | `test_property_migration_completeness.py` |
| 6 | Cache Consistency | Cache matches DynamoDB after provisioning | `test_property_cache_consistency.py` |
| 7 | Write-Behind Completeness | Buffer empty and all records in store after flush | `test_property_buffer_ordering.py` (combined) |
| 8 | Buffer Ordering Preservation | FIFO order strictly preserved during flush | `test_property_buffer_ordering.py` |
| 9 | Pending Context Chat Availability | Verified members always get IsolatedContext regardless of store status | `test_property_pending_context.py` |
| 10 | Isolated Config Construction | MemoryConfig uses family_store_id, not global | `test_property_isolated_config.py` |
| 11 | Migration Report Consistency | migrated + failed + skipped = total families | `test_property_migration_report.py` |
| 12 | Registry Entry Validation | family_id/store_id non-empty, status in allowed set | `test_property_registry_entry.py` |

Additional unit tests:
- `test_isolated_memory_manager.py` — 25 tests covering config building, validation, safe wrappers
- `test_chat_isolation.py` — 4 integration tests for the chat route (active store, pending store, non-member 403, no family_id skip)

## Running Tests

```bash
# All memory-isolation tests (44 tests, ~50s)
python -m pytest \
  backend/tests/test_property_registry_entry.py \
  backend/tests/test_property_store_isolation.py \
  backend/tests/test_property_idempotent_provisioning.py \
  backend/tests/test_property_cache_consistency.py \
  backend/tests/test_property_pending_context.py \
  backend/tests/test_property_isolated_config.py \
  backend/tests/test_property_store_data_affinity.py \
  backend/tests/test_property_buffer_ordering.py \
  backend/tests/test_property_migration_completeness.py \
  backend/tests/test_property_migration_report.py \
  backend/tests/test_isolated_memory_manager.py \
  backend/tests/test_chat_isolation.py \
  -v
```

## File Inventory

```
backend/app/models/agentcore.py              # IsolatedContext, FamilyMemoryStoresItem dataclasses
backend/app/services/family_memory_registry.py  # FamilyMemoryStoreRegistry (cache + DynamoDB + provisioning)
backend/app/services/isolation_middleware.py     # IsolationMiddleware (membership verification + store resolution)
backend/app/services/isolated_memory_manager.py  # IsolatedMemoryManager (per-family MemoryConfig builder)
backend/app/services/memory_write_behind_buffer.py  # MemoryWriteBehindBuffer (FIFO queue for pending stores)
backend/app/routes/chat.py                      # Chat route integration
backend/scripts/migrate_memory_stores.py        # MigrationOrchestrator (one-time shared→isolated migration)
infra/stacks/data_stack.py                      # FamilyMemoryStores DynamoDB table (CDK)
infra/stacks/security_stack.py                  # IAM permissions (CDK)
backend/tests/test_property_*.py                # 10 property-based test files (12 properties)
backend/tests/test_isolated_memory_manager.py   # 25 unit tests
backend/tests/test_chat_isolation.py            # 4 integration tests
```
