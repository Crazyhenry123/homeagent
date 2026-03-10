# Implementation Plan: Multi-Family Memory Isolation

## Overview

Incrementally build infrastructure-enforced memory isolation for HomeAgent families. Each task builds on the previous, starting with data models and CDK infrastructure, then core components (registry, middleware, memory manager), the write-behind buffer for non-blocking chat, and finally the migration orchestrator. Property-based tests validate correctness properties at each step using Hypothesis.

## Tasks

- [x] 1. Define data models and CDK infrastructure
  - [x] 1.1 Create the IsolatedContext and FamilyMemoryStoresItem data models
    - Add `IsolatedContext` dataclass to `backend/app/models/agentcore.py` with fields: family_id, member_id, family_store_id (Optional[str]), is_verified (bool), store_status (str: "active" | "pending"), verified_at (str)
    - Add `FamilyMemoryStoresItem` dataclass with fields: family_id, store_id, store_name, created_at, updated_at, status (str: "active" | "migrating" | "provisioning" | "decommissioned"), event_expiry_days (int, default 365)
    - Add validation methods: family_id/store_id non-empty, status in allowed set, event_expiry_days > 0
    - _Requirements: 4.2, 4.3, 4.4, 8.2_

  - [x] 1.2 Write property test for registry entry validation (Property 12)
    - **Property 12: Registry Entry Validation**
    - Generate random FamilyMemoryStoresItem instances with Hypothesis; assert family_id and store_id are non-empty, status is in {"active", "migrating", "provisioning", "decommissioned"}
    - Use `max_examples=50` for fast execution
    - **Validates: Requirements 4.3, 4.4**

  - [x] 1.3 Add FamilyMemoryStores DynamoDB table to CDK data stack
    - In `infra/stacks/data_stack.py`, add a DynamoDB table with partition key `family_id` (String), on-demand billing, and point-in-time recovery enabled
    - Export the table reference so `SecurityStack` can grant read/write permissions to the ECS task role
    - Wire the new table into `infra/stacks/security_stack.py` to grant the task role read/write access
    - _Requirements: 4.1, 10.1, 10.3, 10.4_

  - [x] 1.4 Add IAM permissions for AgentCore CreateMemory and GetMemory
    - Verify `infra/stacks/security_stack.py` already grants `bedrock-agentcore:CreateMemory` and `bedrock-agentcore:GetMemory` to the ECS task role (it does — confirm no changes needed)
    - _Requirements: 10.2_

- [x] 2. Checkpoint — Verify models and infrastructure
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement FamilyMemoryStoreRegistry
  - [x] 3.1 Create FamilyMemoryStoreRegistry class
    - Create `backend/app/services/family_memory_registry.py`
    - Implement `get_store_id(family_id)`: cache-first lookup, DynamoDB fallback, on-demand provisioning via AgentCore CreateMemory API
    - Implement `get_store_status(family_id)`: returns store_id and status ("active" or "pending")
    - Implement `provision_family_store(family_id)`: calls AgentCore CreateMemory, registers in DynamoDB with conditional write (`attribute_not_exists`), populates cache
    - Implement in-memory cache with 5-minute TTL using a dict + timestamp tracking
    - Handle `ConditionalCheckFailedException` for concurrent provisioning: re-read table and use the winning store_id
    - Implement retry with exponential backoff (max 3 attempts) for CreateMemory failures
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 7.1, 7.5, 9.2, 9.3, 9.4_

  - [x] 3.2 Write property test for store isolation guarantee (Property 1)
    - **Property 1: Store Isolation Guarantee**
    - Generate pairs of distinct family_id values; call `get_store_id` on each; assert returned store_ids are different
    - Use mocked AgentCore control plane and DynamoDB
    - Use `max_examples=50`
    - **Validates: Requirement 2.7**

  - [x] 3.3 Write property test for idempotent provisioning (Property 4)
    - **Property 4: Idempotent Provisioning**
    - Generate a random family_id; call `get_store_id` multiple times; assert all calls return the same store_id
    - Simulate concurrent calls using threading to verify conditional write prevents duplicates
    - Use `max_examples=50`
    - **Validates: Requirements 2.4, 2.6**

  - [x] 3.4 Write property test for cache consistency (Property 6)
    - **Property 6: Cache Consistency**
    - Generate a family_id; provision a store; assert cache entry matches DynamoDB entry
    - Verify that after provisioning, the cache is immediately populated with the correct store_id
    - Use `max_examples=50`
    - **Validates: Requirements 9.1, 9.3, 2.3**

- [x] 4. Implement IsolationMiddleware
  - [x] 4.1 Create IsolationMiddleware class
    - Create `backend/app/services/isolation_middleware.py`
    - Implement `validate_and_resolve(family_id, member_id)`: verify membership via FamilyMembers table query, resolve store via FamilyMemoryStoreRegistry, return IsolatedContext
    - Handle "pending" store status: return IsolatedContext with family_store_id=None, store_status="pending", and kick off async provisioning
    - Handle "active" store with pending buffer: trigger flush before returning context
    - Reject non-members with AccessDeniedError (HTTP 403) and log the attempt with family_id, member_id, timestamp
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 8.1, 8.2, 8.3, 8.4_

  - [x] 4.2 Write property test for membership gate (Property 2)
    - **Property 2: Membership Gate**
    - Generate random family_id/member_id pairs where the member does NOT belong to the family; assert `validate_and_resolve` raises AccessDeniedError
    - Use `max_examples=50`
    - **Validates: Requirements 1.2, 1.4**

  - [x] 4.3 Write property test for pending context chat availability (Property 9)
    - **Property 9: Pending Context Chat Availability**
    - Generate verified family members; call `validate_and_resolve` with store in both "active" and "pending" states; assert an IsolatedContext is always returned (never raises)
    - Use `max_examples=50`
    - **Validates: Requirements 8.1, 8.4**

- [x] 5. Implement IsolatedMemoryManager
  - [x] 5.1 Create IsolatedMemoryManager class
    - Create `backend/app/services/isolated_memory_manager.py`
    - Extend or wrap `AgentCoreMemoryManager` to accept an IsolatedContext instead of global store IDs
    - Implement `build_isolated_memory_config(context, session_id)`: build MemoryConfig with memory_id=context.family_store_id, actor_id=context.family_id for family tier; use shared member store with actor_id=context.member_id for member tier
    - Validate that family_store_id matches the expected store for the family_id before any operation
    - Provide the same `safe_*` wrapper pattern for error handling
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 5.2 Write property test for isolated config construction (Property 10)
    - **Property 10: Isolated Config Construction**
    - Generate IsolatedContext instances with active stores; build MemoryConfig; assert family memory_id equals context.family_store_id (not global), actor_id equals family_id, and member tier uses shared store
    - Use `max_examples=50`
    - **Validates: Requirements 3.1, 3.2, 3.3**

  - [x] 5.3 Write property test for store-data affinity (Property 3)
    - **Property 3: Store-Data Affinity**
    - Generate a family_id and mock memory retrieval; assert all returned records originate from the family's dedicated store_id matching `get_store_id(family_id)`
    - Use `max_examples=50`
    - **Validates: Requirements 3.4, 3.5**

- [x] 6. Checkpoint — Verify core isolation components
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement MemoryWriteBehindBuffer
  - [x] 7.1 Create MemoryWriteBehindBuffer class
    - Create `backend/app/services/memory_write_behind_buffer.py`
    - Define `BufferedMemoryOperation` dataclass: operation_type, family_id, payload (dict), queued_at, attempt_count
    - Define `BufferState` dataclass: family_id, status ("buffering" | "flushing" | "flushed"), operations list, store_id (Optional), created_at, flushed_at (Optional)
    - Implement `buffer_or_execute(family_id, operation, payload)`: if store active, flush pending then execute directly; if pending, enqueue operation
    - Implement `flush_buffer(family_id, store_id)`: flush all buffered ops in FIFO order, retry failed ops up to 3 times, discard after 3 failures with error log
    - Implement `has_pending(family_id)` and `get_buffered_records(family_id, filters)` for retrieve during pending state
    - Enforce max 100 operations per family buffer; evict oldest with warning log on overflow
    - Clean up buffer state after successful full flush
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 7.6_

  - [x] 7.2 Write property test for write-behind completeness (Property 7)
    - **Property 7: Write-Behind Completeness**
    - Generate a sequence of buffered operations for a family; simulate store becoming active; flush; assert buffer is empty and all records exist in the store
    - Use `max_examples=50`
    - **Validates: Requirements 6.3, 6.6, 6.7**

  - [x] 7.3 Write property test for buffer ordering preservation (Property 8)
    - **Property 8: Buffer Ordering Preservation**
    - Generate a sequence of operations with timestamps; buffer them; flush; assert operations were flushed in the exact FIFO order they were queued
    - Use `max_examples=50`
    - **Validates: Requirement 6.1**

- [x] 8. Wire components together and integrate into Flask routes
  - [x] 8.1 Integrate IsolationMiddleware into the chat request path
    - Modify the chat route(s) in `backend/app/routes/` to call `validate_and_resolve` before any memory operation
    - Pass the resulting IsolatedContext to IsolatedMemoryManager instead of the global AgentCoreMemoryManager
    - When store_status is "pending", route memory operations through MemoryWriteBehindBuffer
    - When store_status is "active" with pending buffer, flush before proceeding
    - _Requirements: 1.1, 1.2, 1.3, 3.1, 8.1, 8.4_

  - [x] 8.2 Update AgentCore runtime session creation to use isolated config
    - Modify `backend/app/services/agentcore_memory.py` or the runtime client to accept IsolatedMemoryConfig when building sessions
    - Ensure `create_combined_session_manager` uses the per-family store_id from IsolatedContext
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 8.3 Write unit tests for the integrated chat flow
    - Test chat request with active store: verify IsolatedContext is created, correct store_id used
    - Test chat request with pending store: verify write-behind buffer is used, chat proceeds
    - Test chat request with non-member: verify 403 response
    - _Requirements: 1.4, 3.1, 8.1_

- [x] 9. Checkpoint — Verify end-to-end isolation flow
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement Migration Orchestrator
  - [x] 10.1 Create MigrationOrchestrator class
    - Create `backend/scripts/migrate_memory_stores.py`
    - Implement `migrate_shared_to_isolated(dry_run)`: enumerate distinct family_ids from shared store, provision per-family stores, copy records, verify counts
    - Skip families that already have active dedicated stores
    - Support dry-run mode: log what would be migrated without creating stores or copying records
    - Produce a MigrationReport with migrated, failed, skipped counts
    - Handle per-family failures gracefully: log error, increment failed counter, continue with remaining families
    - Mark stores as "migrating" if record count mismatch after copy
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

  - [x] 10.2 Write property test for migration completeness (Property 5)
    - **Property 5: Migration Completeness**
    - Generate a set of families with random record counts in a mock shared store; run migration; assert each family's dedicated store has the same record count as the source
    - Use `max_examples=50`
    - **Validates: Requirements 5.2, 5.3**

  - [x] 10.3 Write property test for migration report consistency (Property 11)
    - **Property 11: Migration Report Consistency**
    - Generate a set of families (some already migrated, some new, some failing); run migration; assert migrated + failed + skipped equals total distinct family_ids
    - Use `max_examples=50`
    - **Validates: Requirements 5.5, 5.8**

- [x] 11. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- All property-based tests use Hypothesis with `max_examples=50` for fast execution
- Each task references specific requirements for traceability
- The write-behind buffer (task 7) is critical — it ensures chat is never blocked during store provisioning
- Task 1.4 is a verification step; the existing security stack already grants the needed AgentCore IAM permissions
- Python is the implementation language throughout (Flask backend, CDK infrastructure, Hypothesis tests)
