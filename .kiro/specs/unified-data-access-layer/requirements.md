# Requirements Document

## Introduction

HomeAgent currently uses Amazon DynamoDB across 22 tables with direct `get_table()` calls scattered throughout 15+ service modules. Database access logic (query construction, update expressions, error handling, pagination) is duplicated in every service. A partial `StorageProvider` abstraction exists but only covers health-related tables (4 of 22). This spec defines a unified data access layer (DAL) that centralizes all database operations behind a consistent interface, evaluates DynamoDB fitness for the workload, and optimizes the data model for extensibility.

## Glossary

- **DAL**: Data Access Layer — the unified abstraction module that encapsulates all database operations behind a consistent Python interface.
- **Repository**: A DAL component responsible for CRUD operations on a single logical entity (e.g., `UserRepository`, `ConversationRepository`).
- **DynamoDB**: Amazon's fully managed NoSQL key-value and document database, currently used as the sole database for HomeAgent.
- **GSI**: Global Secondary Index — a DynamoDB index with a different partition key and optional sort key from the base table, enabling alternate query patterns.
- **TTL**: Time-To-Live — a DynamoDB feature that automatically deletes expired items based on a timestamp attribute.
- **Single-Table Design**: A DynamoDB pattern where multiple entity types share one table, using composite keys to distinguish them.
- **Service_Layer**: The existing `backend/app/services/` modules that contain business logic and currently make direct DynamoDB calls.
- **StorageProvider**: The existing abstract base class in `backend/app/storage/base.py` that defines a pluggable storage interface, currently only used for health records and observations.
- **Table_Definitions**: The `TABLE_DEFINITIONS` dictionary in `backend/app/models/dynamo.py` that declares all 22 DynamoDB table schemas.
- **Entity**: A distinct data type stored in the database (e.g., User, Conversation, Message, HealthRecord).
- **Write-Behind_Buffer**: The existing `memory_write_behind_buffer.py` pattern that batches writes for performance.

## Requirements

### Requirement 1: Database Evaluation and Recommendation

**User Story:** As a technical lead, I want a documented evaluation of DynamoDB versus alternatives for HomeAgent's workload, so that the team can make an informed decision on whether to keep, replace, or supplement DynamoDB.

#### Acceptance Criteria

1. THE DAL SHALL include a documented evaluation comparing DynamoDB against at least two alternative databases (e.g., PostgreSQL via Aurora Serverless, MongoDB Atlas) across the following dimensions: query flexibility, cost at projected scale, operational overhead, latency for key access patterns, and schema evolution support.
2. THE DAL evaluation SHALL analyze all 22 existing DynamoDB tables and classify each table's access patterns as key-value lookup, single-entity query, cross-entity join, full-text search, or aggregation.
3. THE DAL evaluation SHALL identify access patterns that are poorly served by DynamoDB (e.g., full table scans in `list_profiles()`, `get_family_tree()`, and `list_templates()`) and recommend specific mitigations or alternative storage for those patterns.
4. WHEN the evaluation recommends keeping DynamoDB, THE DAL evaluation SHALL document the specific DynamoDB best practices that the current implementation violates and provide remediation steps.
5. WHEN the evaluation recommends supplementing DynamoDB with an additional database, THE DAL evaluation SHALL specify which entities move to the new store and provide a migration strategy that maintains zero downtime.

### Requirement 2: Unified Repository Interface

**User Story:** As a developer, I want a single consistent interface for all database operations, so that I do not need to write raw DynamoDB expressions in service code.

#### Acceptance Criteria

1. THE DAL SHALL expose a base `Repository` class that provides typed methods for `create`, `get_by_id`, `query`, `update`, `delete`, and `batch_delete` operations.
2. THE DAL SHALL provide a concrete Repository implementation for each of the following entities: User, Device, InviteCode, Family, FamilyMember, Conversation, Message, MemberProfile, AgentConfig, AgentTemplate, FamilyRelationship, HealthRecord, HealthObservation, HealthAuditLog, HealthDocument, ChatMedia, MemberPermission, MemorySharingConfig, StorageConfig, OAuthToken, OAuthState, FamilyGroup, and FamilyMemoryStore.
3. THE DAL Repository implementations SHALL encapsulate all DynamoDB-specific logic including `KeyConditionExpression`, `UpdateExpression`, `ExpressionAttributeNames`, `ExpressionAttributeValues`, `ConditionExpression`, and `ProjectionExpression` construction.
4. THE DAL Repository methods SHALL accept and return plain Python dictionaries or typed dataclasses, not boto3 response objects.
5. THE DAL SHALL provide a `UnitOfWork` or transaction helper that wraps DynamoDB `TransactWriteItems` for operations that modify multiple tables atomically (e.g., creating a family and updating the owner user record).

### Requirement 3: Service Layer Migration

**User Story:** As a developer, I want all service modules to use the DAL instead of direct `get_table()` calls, so that database access is consistent and testable.

#### Acceptance Criteria

1. WHEN the DAL is complete, THE Service_Layer SHALL use Repository instances for all database operations instead of calling `get_table()` directly.
2. THE Service_Layer migration SHALL remove all direct imports of `get_table` and `get_dynamodb` from service modules.
3. THE Service_Layer migration SHALL preserve all existing API behavior, including response formats, error codes, and pagination cursors.
4. THE Service_Layer migration SHALL consolidate the existing `StorageProvider` abstraction into the DAL, replacing the dual code paths (storage provider vs. direct DynamoDB) in `health_records.py`, `health_observations.py`, and `health_documents.py` with a single Repository-based path.
5. IF a service module currently uses `table.scan()` for listing operations, THEN THE DAL SHALL provide an indexed query alternative or document the scan as an accepted trade-off with a size-bounded safeguard.

### Requirement 4: Data Model Optimization

**User Story:** As a developer, I want the data model to be properly structured and easy to extend, so that adding new features does not require schema migrations or new tables.

#### Acceptance Criteria

1. THE DAL SHALL define a canonical schema for each entity as a Python dataclass or TypedDict with explicit field names, types, and default values.
2. THE DAL canonical schemas SHALL include `created_at` and `updated_at` ISO-8601 timestamp fields on every entity that supports mutation.
3. THE DAL SHALL add a `version` field to entities that support concurrent updates (User, MemberProfile, AgentConfig, HealthRecord) to enable optimistic locking via DynamoDB conditional writes.
4. THE DAL SHALL normalize the key schema for the FamilyMembers and FamilyGroups tables, which currently store overlapping family membership data, into a single canonical membership entity with a clear GSI for reverse lookups (member → families).
5. THE DAL SHALL add a GSI on the Messages table with partition key `conversation_id` and sort key `created_at` to support time-range queries without relying on the composite `sort_key` format.
6. WHEN a new entity type is added to the system, THE DAL SHALL support the addition by creating a new Repository subclass and registering the schema, without modifying existing Repository implementations.

### Requirement 5: Error Handling and Resilience

**User Story:** As a developer, I want the DAL to handle database errors consistently, so that service code does not need to catch boto3-specific exceptions.

#### Acceptance Criteria

1. THE DAL SHALL define a hierarchy of database-agnostic exception classes: `EntityNotFoundError`, `DuplicateEntityError`, `ConditionalCheckError`, `TransactionConflictError`, and `DataAccessError`.
2. THE DAL SHALL translate all boto3 `ClientError` and `ConditionalCheckFailedException` exceptions into the corresponding DAL exception before propagating to the Service_Layer.
3. WHEN a DynamoDB throttling event occurs, THE DAL SHALL retry the operation with exponential backoff up to 3 attempts before raising a `DataAccessError`.
4. THE DAL SHALL log all database errors with structured fields including table name, operation type, key values, and latency.

### Requirement 6: Query and Pagination Standardization

**User Story:** As a developer, I want a consistent pagination interface across all list/query operations, so that API routes do not need to construct DynamoDB-specific pagination tokens.

#### Acceptance Criteria

1. THE DAL SHALL provide a `PaginatedResult` type that contains `items: list`, `next_cursor: str | None`, and `count: int` fields.
2. THE DAL query methods SHALL accept an opaque `cursor: str | None` parameter and a `limit: int` parameter for forward pagination.
3. THE DAL SHALL encode and decode DynamoDB `LastEvaluatedKey` dictionaries into opaque, URL-safe cursor strings so that API consumers do not receive raw DynamoDB key structures.
4. WHEN a query returns no results, THE DAL SHALL return a `PaginatedResult` with an empty `items` list and `next_cursor` set to `None`.

### Requirement 7: Testing and Observability

**User Story:** As a developer, I want the DAL to be independently testable and observable, so that I can verify database operations without running a full application stack.

#### Acceptance Criteria

1. THE DAL SHALL support dependency injection of the DynamoDB resource, allowing tests to provide a DynamoDB Local or mocked resource without patching module-level globals.
2. THE DAL SHALL provide an in-memory Repository implementation that stores data in Python dictionaries, suitable for unit tests that do not require DynamoDB.
3. THE DAL SHALL emit timing metrics for each database operation (get, put, query, update, delete) as structured log entries with operation name, table name, and duration in milliseconds.
4. THE DAL integration tests SHALL verify round-trip correctness: for each entity type, creating an entity then reading the entity back SHALL produce an equivalent object.

### Requirement 8: Backward Compatibility and Migration Path

**User Story:** As a developer, I want to migrate to the DAL incrementally without breaking existing functionality, so that the migration can be done service-by-service.

#### Acceptance Criteria

1. THE DAL SHALL coexist with the existing `get_table()` function during the migration period, allowing services to be migrated one at a time.
2. THE DAL SHALL use the same DynamoDB table names and key schemas as the existing `TABLE_DEFINITIONS` dictionary, requiring zero table-level infrastructure changes for the initial rollout.
3. THE DAL SHALL preserve the existing `TABLE_PREFIX` configuration for table name resolution, supporting both production and local development environments.
4. WHEN a service is migrated to use the DAL, THE existing API tests for that service SHALL continue to pass without modification.
