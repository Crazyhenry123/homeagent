# Requirements Document

## Introduction

HomeAgent currently uses two global AgentCore Memory stores shared across all families, relying on application-level filtering by `family_id` for isolation. This is fragile — a bug in filtering logic could leak one family's private memories to another. This feature introduces infrastructure-enforced memory isolation by provisioning per-family AgentCore Memory stores, enforcing family membership at the middleware layer, and adding a DynamoDB-backed registry for family-to-store mapping. A write-behind buffer ensures chat availability is never blocked by store provisioning.

## Glossary

- **IsolationMiddleware**: Flask middleware component that intercepts every request touching family memory, verifies family membership, and resolves the per-family store ID
- **FamilyMemoryStoreRegistry**: Component that maps each family_id to a dedicated AgentCore Memory store ID, provisions new stores on-demand, and caches mappings
- **IsolatedMemoryManager**: Component that replaces the global AgentCoreMemoryManager, building MemoryConfig objects scoped to per-family store IDs
- **FamilyMemoryStores_Table**: DynamoDB table that persistently maps family_id to AgentCore Memory store IDs
- **MigrationOrchestrator**: One-time migration tool that copies records from the shared global store into per-family isolated stores
- **MemoryWriteBehindBuffer**: Server-side write-behind cache that queues memory operations when a family's store is not yet provisioned and flushes them once the store becomes active
- **IsolatedContext**: Request-scoped data structure containing family_id, member_id, family_store_id, verification status, and store status
- **AgentCore_Memory**: Amazon Bedrock AgentCore Memory service used for per-family store provisioning and memory operations
- **FamilyGroups_Table**: Existing DynamoDB table that records family membership (which members belong to which families)
- **BufferedMemoryOperation**: Data structure representing a queued memory operation including operation type, payload, timestamp, and attempt count

## Requirements

### Requirement 1: Family Membership Verification

**User Story:** As a HomeAgent family member, I want the system to verify my family membership before any memory operation, so that unauthorized users cannot access my family's private memories.

#### Acceptance Criteria

1. WHEN a request touches family memory, THE IsolationMiddleware SHALL extract family_id and member_id from the authenticated Cognito JWT claims
2. WHEN the IsolationMiddleware receives a request, THE IsolationMiddleware SHALL verify that the member_id belongs to the family_id by querying the FamilyGroups_Table
3. WHEN membership verification succeeds, THE IsolationMiddleware SHALL attach an IsolatedContext with is_verified set to TRUE to the request
4. WHEN a member_id is not found in the FamilyGroups_Table for the given family_id, THE IsolationMiddleware SHALL reject the request with HTTP 403 and message "Access denied: not a member of this family"
5. WHEN membership verification fails, THE IsolationMiddleware SHALL log the attempt with family_id, member_id, and timestamp for security audit

### Requirement 2: Per-Family Store Resolution and Provisioning

**User Story:** As a HomeAgent system, I want each family to have a dedicated AgentCore Memory store, so that cross-family data leakage is architecturally impossible.

#### Acceptance Criteria

1. WHEN the IsolationMiddleware resolves a store for a family_id, THE FamilyMemoryStoreRegistry SHALL first check the in-memory cache for a cached store_id
2. WHEN the cache does not contain a store_id for the family_id, THE FamilyMemoryStoreRegistry SHALL query the FamilyMemoryStores_Table for the mapping
3. WHEN the FamilyMemoryStores_Table contains an active entry for the family_id, THE FamilyMemoryStoreRegistry SHALL return the store_id and populate the cache with a 5-minute TTL
4. WHEN no store exists for a family_id, THE FamilyMemoryStoreRegistry SHALL provision a new AgentCore Memory store via the CreateMemory API with name "family_{family_id}"
5. WHEN a new store is provisioned, THE FamilyMemoryStoreRegistry SHALL register the mapping in the FamilyMemoryStores_Table using a conditional write (attribute_not_exists) to prevent duplicates
6. WHEN two concurrent requests attempt to provision a store for the same family_id, THE FamilyMemoryStoreRegistry SHALL ensure only one store is created by using DynamoDB conditional writes, with the losing request re-reading the table to use the winning store_id
7. FOR ALL distinct family_id values family_a and family_b, THE FamilyMemoryStoreRegistry SHALL return distinct store_id values

### Requirement 3: Isolated Memory Configuration

**User Story:** As a HomeAgent developer, I want memory operations to use per-family store IDs instead of global store IDs, so that each family's data is physically separated.

#### Acceptance Criteria

1. WHEN building a MemoryConfig for a chat session, THE IsolatedMemoryManager SHALL use the family_store_id from the IsolatedContext instead of the global AGENTCORE_FAMILY_MEMORY_ID
2. WHEN building a MemoryConfig, THE IsolatedMemoryManager SHALL set the actor_id to the family_id from the IsolatedContext
3. WHEN building a MemoryConfig for member-tier memory, THE IsolatedMemoryManager SHALL continue using the shared member store scoped by member_id as actor_id
4. WHEN the IsolatedMemoryManager receives an IsolatedContext, THE IsolatedMemoryManager SHALL validate that the family_store_id matches the expected store for the family_id before executing any operation
5. WHEN retrieving family memory through an IsolatedContext, THE IsolatedMemoryManager SHALL return only records from the family's dedicated store

### Requirement 4: FamilyMemoryStores DynamoDB Table

**User Story:** As a HomeAgent system, I want a persistent registry mapping families to their dedicated memory stores, so that store assignments survive restarts and are consistent across all backend instances.

#### Acceptance Criteria

1. THE FamilyMemoryStores_Table SHALL use family_id as the partition key
2. THE FamilyMemoryStores_Table SHALL store store_id, store_name, created_at, updated_at, status, and event_expiry_days for each entry
3. WHEN a new entry is written, THE FamilyMemoryStores_Table SHALL enforce that family_id and store_id are non-empty strings
4. THE FamilyMemoryStores_Table SHALL restrict the status field to one of: "active", "migrating", "provisioning", or "decommissioned"
5. WHEN a store is decommissioned, THE FamilyMemoryStores_Table SHALL retain the entry for audit and recovery purposes rather than deleting it

### Requirement 5: Data Migration from Shared to Isolated Stores

**User Story:** As a HomeAgent operator, I want to migrate existing family memory records from the shared global store into per-family isolated stores, so that all families benefit from infrastructure-enforced isolation.

#### Acceptance Criteria

1. WHEN the MigrationOrchestrator runs, THE MigrationOrchestrator SHALL enumerate all distinct family_id values from the existing shared store
2. WHEN processing a family_id, THE MigrationOrchestrator SHALL provision a dedicated store and copy all records belonging to that family_id into the new store
3. WHEN migration completes for a family_id, THE MigrationOrchestrator SHALL verify that the record count in the dedicated store matches the record count from the shared store for that family_id
4. WHEN the record count does not match after migration, THE MigrationOrchestrator SHALL mark the family's store status as "migrating" and log the discrepancy
5. WHEN a family_id already has an active dedicated store, THE MigrationOrchestrator SHALL skip that family and increment the skipped counter
6. WHEN the MigrationOrchestrator is run in dry-run mode, THE MigrationOrchestrator SHALL log what would be migrated without creating stores or copying records
7. WHEN migration fails for a family_id, THE MigrationOrchestrator SHALL log the error, increment the failed counter, and continue processing remaining families
8. THE MigrationOrchestrator SHALL produce a MigrationReport containing counts of migrated, failed, and skipped families

### Requirement 6: Write-Behind Buffer for Pending Stores

**User Story:** As a HomeAgent family member, I want to start chatting immediately after family registration without waiting for store provisioning, so that my experience is seamless.

#### Acceptance Criteria

1. WHEN a memory operation is requested and the family's store status is "pending", THE MemoryWriteBehindBuffer SHALL queue the operation in-memory with a timestamp and preserve FIFO ordering
2. WHEN a retrieve operation is requested while the store is pending, THE MemoryWriteBehindBuffer SHALL return buffered records that match the query filters
3. WHEN the family's store becomes active, THE MemoryWriteBehindBuffer SHALL flush all buffered operations to the dedicated store in FIFO order
4. WHEN a buffered operation fails during flush, THE MemoryWriteBehindBuffer SHALL increment the attempt_count and retain the operation for retry
5. WHEN a buffered operation has failed 3 times, THE MemoryWriteBehindBuffer SHALL log the operation with full payload as a permanent failure and discard it
6. WHEN all buffered operations for a family are successfully flushed, THE MemoryWriteBehindBuffer SHALL remove the buffer state for that family to free memory
7. WHEN a request arrives for a family with an active store that has pending buffered operations, THE MemoryWriteBehindBuffer SHALL flush the pending operations before executing the new operation
8. WHEN the buffer for a family exceeds 100 operations, THE MemoryWriteBehindBuffer SHALL evict the oldest operations with a warning log containing the full payload for manual recovery

### Requirement 7: Error Handling and Resilience

**User Story:** As a HomeAgent system, I want graceful error handling for all isolation components, so that transient failures do not break the chat experience.

#### Acceptance Criteria

1. WHEN the AgentCore CreateMemory API call fails during store provisioning, THE FamilyMemoryStoreRegistry SHALL retry with exponential backoff up to 3 attempts
2. IF all provisioning retries fail, THEN THE FamilyMemoryStoreRegistry SHALL allow the request to proceed without family memory in stateless mode and retry provisioning on the next request
3. WHEN the FamilyMemoryStores_Table is unreachable, THE FamilyMemoryStoreRegistry SHALL serve the store_id from cache if a valid cache entry exists
4. IF the FamilyMemoryStores_Table is unreachable and no cache entry exists, THEN THE FamilyMemoryStoreRegistry SHALL return HTTP 503 with message "Memory service temporarily unavailable"
5. WHEN a DynamoDB conditional write conflict occurs during provisioning, THE FamilyMemoryStoreRegistry SHALL re-read the table and use the store_id written by the winning request
6. WHEN a flush failure occurs for buffered operations, THE MemoryWriteBehindBuffer SHALL retain failed operations and attempt flush on the next request for that family

### Requirement 8: Chat Availability During Provisioning

**User Story:** As a HomeAgent family member, I want chat to always be available regardless of store provisioning status, so that I am never blocked from using the assistant.

#### Acceptance Criteria

1. WHEN a verified family member initiates a chat request, THE IsolationMiddleware SHALL return an IsolatedContext regardless of whether the store_status is "active" or "pending"
2. WHEN the store_status is "pending", THE IsolationMiddleware SHALL set family_store_id to NULL and store_status to "pending" in the IsolatedContext
3. WHEN the store_status is "pending" and no FamilyMemoryStores_Table entry exists, THE IsolationMiddleware SHALL initiate asynchronous store provisioning
4. WHEN the store becomes active on a subsequent request, THE IsolationMiddleware SHALL flush any pending buffer before returning the IsolatedContext with store_status "active"

### Requirement 9: Cache Consistency

**User Story:** As a HomeAgent system, I want the in-memory store_id cache to remain consistent with the DynamoDB source of truth, so that requests are never routed to incorrect stores.

#### Acceptance Criteria

1. WHEN a cache entry exists for a family_id, THE FamilyMemoryStoreRegistry SHALL ensure the cached store_id matches the store_id in the FamilyMemoryStores_Table
2. THE FamilyMemoryStoreRegistry SHALL set a TTL of 5 minutes on all cache entries to bound staleness
3. WHEN a new store is provisioned, THE FamilyMemoryStoreRegistry SHALL immediately populate the cache with the new store_id
4. WHEN a cache miss occurs, THE FamilyMemoryStoreRegistry SHALL fall through to DynamoDB lookup and repopulate the cache on success

### Requirement 10: Infrastructure as Code

**User Story:** As a HomeAgent developer, I want all new infrastructure for memory isolation defined in CDK, so that deployments are repeatable and auditable.

#### Acceptance Criteria

1. THE CDK_Stack SHALL define the FamilyMemoryStores DynamoDB table with family_id as partition key and on-demand billing
2. THE CDK_Stack SHALL grant the ECS task role IAM permissions for bedrock-agentcore:CreateMemory and bedrock-agentcore:GetMemory
3. THE CDK_Stack SHALL grant the ECS task role read/write permissions on the FamilyMemoryStores DynamoDB table
4. THE CDK_Stack SHALL define the FamilyMemoryStores table with point-in-time recovery enabled for data protection
