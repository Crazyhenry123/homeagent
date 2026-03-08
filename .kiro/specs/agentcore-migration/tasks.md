# Implementation Plan: AgentCore Migration

## Overview

Migrate the HomeAgent family agent platform from custom Strands Agent orchestration to Amazon Bedrock AgentCore across five pillars: Runtime, Agent Management, Memory, Gateway, and Identity. Implementation uses Python with Flask, boto3, and the bedrock-agentcore SDK. Tasks are ordered to build foundational components first (config, data models, identity), then core services (agent management, memory, gateway), then runtime integration, and finally wiring everything together.

## Tasks

- [x] 1. Infrastructure and configuration foundation
  - [x] 1.1 Add AgentCore configuration to Config class
    - Add environment variable bindings for AGENTCORE_ORCHESTRATOR_AGENT_ID, AGENTCORE_RUNTIME_ENDPOINT, AGENTCORE_FAMILY_MEMORY_ID, AGENTCORE_MEMBER_MEMORY_ID, AGENTCORE_GATEWAY_ID, HEALTH_MCP_ENDPOINT, FAMILY_MCP_ENDPOINT, COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID
    - _Requirements: 29.3_

  - [x] 1.2 Create CDK stack for AgentCore resources
    - Provision Cognito User Pool with email sign-in, custom attributes (family_id, app_role), self-sign-up disabled
    - Provision DynamoDB tables: FamilyMemories (family_id HASH, memory_key RANGE, category-index GSI, updated-index GSI), MemberMemories (member_id HASH, session_id RANGE, created-index GSI), FamilyGroups (family_id HASH, member_id RANGE, member-family-index GSI)
    - All tables use PAY_PER_REQUEST billing mode
    - _Requirements: 29.1, 29.2, 29.4, 29.5, 29.6, 29.7_

  - [x] 1.3 Create data model classes
    - Define AgentTemplate, AgentConfig, SubAgentToolConfig, FamilyMemoryRecord, MemberMemoryRecord, IdentityContext, StreamEvent, CombinedSessionManager, MemoryConfig dataclasses
    - Include validation rules: agent_type uniqueness, available_to format, category enum, memory_key format, content max length 10000
    - _Requirements: 4.1, 4.2, 6.4, 14.3, 14.4, 14.5_

  - [x] 1.4 Write property tests for data model validation
    - **Property 25: Agent Type Uniqueness** — for any two AgentTemplates, their agent_type values are distinct
    - **Validates: Requirements 4.2**

  - [x] 1.5 Write property tests for config merge precedence
    - **Property 18: Config Merge Precedence** — for any template default_config and user overrides, merged config contains all defaults with user overrides taking precedence
    - **Validates: Requirements 5.6**

  - [x] 1.6 Update Users table schema for Cognito integration
    - Add cognito_sub field and family_id field to Users table
    - Create cognito_sub-index GSI (HASH: cognito_sub) for token-to-user lookup
    - _Requirements: 19.2_

- [x] 2. Checkpoint — Ensure all tests pass, ask the user if questions arise.

- [x] 3. AgentCore Identity Middleware
  - [x] 3.1 Implement AgentCoreIdentityMiddleware class
    - Implement validate_token() to verify JWT against Cognito User Pool with cached JWKS (1-hour TTL)
    - Implement require_auth decorator: extract Bearer token, validate, resolve cognito_sub to user_id/family_id/role, set g.user_id, g.family_id, g.user_role, g.cognito_sub
    - Implement require_role decorator for RBAC enforcement
    - Handle error cases: missing/malformed Authorization header (401), expired token (401 TOKEN_EXPIRED), unknown provider (401), user not registered (401), wrong role (403)
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 18.1, 18.2, 18.3_

  - [x] 3.2 Write property tests for authentication token validation
    - **Property 13: Authentication Token Validation** — for any request with Authorization header, valid JWT sets all four context fields; missing/malformed/invalid/expired tokens return 401
    - **Validates: Requirements 17.1, 17.2, 17.3, 17.4, 17.6**

  - [x] 3.3 Write property tests for role-based access enforcement
    - **Property 14: Role-Based Access Enforcement** — for any authenticated user whose role does not match a route's required role, middleware returns 403
    - **Validates: Requirements 18.1, 18.2**

  - [x] 3.4 Implement dual-auth mode for migration period
    - Support both device-token and Cognito JWT authentication in the middleware
    - Try JWT validation first, fall back to device-token lookup if JWT fails
    - _Requirements: 19.5, 31.5_

  - [x] 3.5 Implement family group resolution
    - Look up family_id for authenticated user via FamilyGroups table (member-family-index GSI)
    - If no family_id mapping exists, proceed with member-only memory and log warning
    - Auto-create single-member family group on first login if no family exists
    - _Requirements: 24.1, 24.2_

  - [x] 3.6 Write property tests for family membership validation
    - **Property 22: Family Membership Validation** — for any (family_id, member_id) pair, system verifies membership; users without family_id proceed with member-only memory
    - **Validates: Requirements 12.5, 24.1**

- [x] 4. Checkpoint — Ensure all tests pass, ask the user if questions arise.

- [x] 5. Agent Management Client
  - [x] 5.1 Implement AgentTemplate CRUD operations
    - Implement create_agent_template() with unique agent_type enforcement, all required fields (template_id, agent_type, name, description, system_prompt, tool_server_ids, default_config, available_to, is_builtin, created_by, timestamps)
    - Implement get_template(), get_template_by_type(), list_templates(), get_available_templates(user_id)
    - Implement update_template() with timestamp update
    - Implement delete_template() with built-in protection (reject if is_builtin==True) and cascade-delete of all AgentConfigs referencing the deleted template's agent_type
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.7, 27.1_

  - [x] 5.2 Write property tests for template deletion cascade
    - **Property 23: Template Deletion Cascade** — for any non-builtin template deleted, all referencing AgentConfigs are also deleted; built-in templates cannot be deleted; Gateway routing tool is NOT deleted
    - **Validates: Requirements 4.4, 4.5, 27.1, 27.2**

  - [x] 5.3 Implement built-in template seeding
    - On startup, check for existence of health_advisor, logistics_assistant, shopping_assistant templates
    - Create missing templates with predefined system_prompt, tool_server_ids, available_to="all", is_builtin=True, created_by="system"
    - Do not overwrite existing templates
    - _Requirements: 4.6, 28.1, 28.2, 28.3, 28.4_

  - [x] 5.4 Write property tests for template seeding idempotence
    - **Property 24: Template Seeding Idempotence** — for any startup, seeding creates missing built-in templates and leaves existing ones unchanged; seeded templates have is_builtin==True and created_by=="system"
    - **Validates: Requirements 28.1, 28.2, 28.3, 28.4**

  - [x] 5.5 Implement per-user AgentConfig operations
    - Implement put_user_agent_config(): validate agent_type references valid template, check available_to authorization, merge config (template defaults + user overrides with user precedence), store resolved gateway_tool_id
    - Implement get_user_agent_configs(), get_user_agent_config()
    - Implement delete_user_agent_config()
    - Implement enable/disable by updating enabled field
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [x] 5.6 Implement template authorization enforcement
    - Implement is_user_authorized_for_template(): return True if available_to=="all" or user_id in available_to list
    - Validate available_to is either "all" or non-empty list of valid user_ids
    - Check authorization at both config creation time and session tool resolution time
    - When available_to is updated to remove a user_id, exclude that user's routing tool from future sessions without deleting existing AgentConfig
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 5.7 Write property tests for sub-agent authorization enforcement
    - **Property 1: Sub-Agent Authorization Enforcement** — for any user_id and agent_type, tool is included iff config exists with enabled==True AND user is authorized for template
    - **Validates: Requirements 2.4, 6.1, 6.2, 6.5, 8.1**

  - [x] 5.8 Write property tests for template available_to enforcement
    - **Property 6: Template Available_To Enforcement** — for any template with available_to as a list, only listed user_ids can enable the agent and have the routing tool in their session
    - **Validates: Requirements 5.5, 6.2, 6.3, 6.4**

  - [x] 5.9 Implement admin-only cross-user configuration
    - When requesting_user_id != target user_id, verify requesting user has role "admin"
    - Non-admin cross-user modification returns HTTP 403
    - Users can always modify their own config regardless of role (if authorized for template)
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 5.10 Write property tests for admin-only cross-user configuration
    - **Property 5: Admin-Only Cross-User Configuration** — for any cross-user config modification, operation succeeds only if requesting user has role=="admin"
    - **Validates: Requirements 7.1, 7.2, 7.3**

  - [x] 5.11 Implement sub-agent tool resolution
    - Implement build_sub_agent_tool_ids(): query user's AgentConfigs, filter enabled==True, check authorization for each template, resolve gateway_tool_id, return sorted by agent_type
    - Skip configs with missing templates and log warning
    - Cache resolved tool IDs per user with 60s TTL
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 30.4_

  - [x] 5.12 Write property tests for tool resolution determinism
    - **Property 27: Tool Resolution Determinism** — for any user, resolved tool IDs are sorted by agent_type; configs referencing missing templates are excluded with logged warning
    - **Validates: Requirements 8.2, 8.3, 27.3**

- [x] 6. Checkpoint — Ensure all tests pass, ask the user if questions arise.

- [x] 7. AgentCore Memory Manager
  - [x] 7.1 Implement dual-tier memory configuration
    - Implement get_family_memory_config(): configure family memory store with family_id as actor_id, namespaces /family/{actorId}/health and /family/{actorId}/preferences
    - Implement get_member_memory_config(): configure member memory store with member_id as actor_id, namespaces /member/{actorId}/context and /member/{actorId}/summaries/{sessionId}
    - Use distinct memory store IDs for family and member stores
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 13.4_

  - [x] 7.2 Implement CombinedSessionManager
    - Implement create_combined_session_manager(): verify member_id belongs to family_id, build both memory configs, return combined manager
    - Execute family and member memory retrievals in parallel for <200ms combined latency
    - _Requirements: 12.5, 30.1_

  - [x] 7.3 Write property tests for combined session manager actor routing
    - **Property 9: Combined Session Manager Actor Routing** — for any valid (family_id, member_id, session_id) triple, family config uses family_id as actor_id with correct namespaces, member config uses member_id as actor_id with correct namespaces
    - **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**

  - [x] 7.4 Implement family long-term memory operations
    - Implement store_family_memory(): store without TTL, validate category (health/preferences/context), enforce 10000 char max, use hierarchical memory_key format
    - Implement retrieve_family_memory(): return records for family_id only from family memory store
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [x] 7.5 Write property tests for family memory persistence
    - **Property 10: Family Memory Persistence** — for any family memory record, it persists without TTL, category is valid, content ≤ 10000 chars, memory_key follows format
    - **Validates: Requirements 14.1, 14.2, 14.3, 14.4, 14.5**

  - [x] 7.6 Implement member short-term memory operations
    - Implement store_member_memory(): set 30-day TTL from creation, scope by member_id and session_id
    - Implement retrieve_member_memory(): return records for member_id only from member memory store
    - Increment message_count on each session interaction
    - _Requirements: 15.1, 15.2, 15.3_

  - [x] 7.7 Write property tests for member memory expiry
    - **Property 11: Member Memory Expiry** — for any member memory record, TTL is 30 days from creation, scoped by member_id and session_id, message_count increments on interaction
    - **Validates: Requirements 15.1, 15.2, 15.3, 31.1**

  - [x] 7.8 Write property tests for memory tier isolation
    - **Property 7: Memory Tier Isolation** — for any family_id and member_id, family memory queries never return member records and vice versa; distinct store IDs
    - **Validates: Requirements 13.1, 13.2, 13.3, 13.4**

  - [x] 7.9 Write property tests for family scope correctness
    - **Property 12: Family Scope Correctness** — for any user, combined retrieval includes all family records for their family_id and only their own member records; excludes other members' records
    - **Validates: Requirements 16.1, 16.2, 16.3**

  - [x] 7.10 Implement memory error handling
    - On retrieval failure: log warning, proceed without memory context
    - On storage failure: queue failed operation for background retry
    - Support stateless mode when memory service is unavailable
    - _Requirements: 22.1, 22.2, 22.3_

  - [x] 7.11 Write property tests for memory graceful degradation
    - **Property 20: Memory Graceful Degradation** — for any memory service failure during retrieval, system logs warning and proceeds without memory context in stateless mode
    - **Validates: Requirements 22.1, 22.3**

- [x] 8. Checkpoint — Ensure all tests pass, ask the user if questions arise.

- [x] 9. AgentCore Gateway Manager
  - [x] 9.1 Implement two-level gateway tool architecture
    - Implement register_sub_agent_routing_tool(): register orchestrator-level routing tools (ask_health_advisor, ask_shopping_assistant, etc.)
    - Implement register_mcp_server() and register_tool_server(): register sub-agent-level domain tools as MCP server endpoints with IAM authentication
    - Implement get_orchestrator_tools() and get_sub_agent_tools(): resolve tools per level
    - Maintain disjoint tool sets between orchestrator and sub-agent levels
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 9.2 Write property tests for gateway two-level tool isolation
    - **Property 17: Gateway Two-Level Tool Isolation** — orchestrator tool set contains only routing tools; sub-agent tool set contains only domain tools; no cross-level access
    - **Validates: Requirements 9.1, 9.4, 9.5**

  - [x] 9.3 Implement built-in agent tool registration
    - Register health tools MCP server with all 6 health tools (get_family_health_records, get_health_summary, save_health_observation, get_health_observations, get_family_health_context, search_health_conversations)
    - Register family tree tools MCP server
    - Configure IAM-based authentication for all MCP servers
    - Support dynamic tool registration when new templates are created
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 9.4 Implement built-in vs custom agent handling
    - Route both built-in and custom agents through same authorization, configuration, and routing paths
    - Built-in agents receive pre-registered MCP domain tools + system_prompt
    - Custom agents use template-defined system_prompt as primary driver with optional generic MCP tools
    - Both represented as routing tools at orchestrator level
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [x] 9.5 Write property tests for built-in vs custom agent parity
    - **Property 4: Built-in vs Custom Agent Parity** — both built-in and custom agents follow same authorization/config/routing paths; only difference is MCP tool availability
    - **Validates: Requirements 11.1, 11.3, 11.4**

  - [x] 9.6 Implement gateway error handling
    - Report MCP server errors to agent runtime
    - Allow agent LLM to handle tool errors and communicate unavailability to user
    - Implement health checks on registered MCP servers; temporarily remove unhealthy servers
    - _Requirements: 23.1, 23.2, 23.3_

  - [x] 9.7 Write property tests for tool parity
    - **Property 16: Tool Parity** — for any tool in the current Strands Agent system, it is registered in Gateway and produces equivalent results via MCP
    - **Validates: Requirements 26.1, 26.2**

  - [x] 9.8 Implement tool versioning support
    - Support tool versioning and updates via Gateway API
    - _Requirements: 26.3_

- [x] 10. Checkpoint — Ensure all tests pass, ask the user if questions arise.

- [x] 11. AgentCore Runtime Client
  - [x] 11.1 Implement orchestrator session management
    - Implement create_session(): create orchestrator runtime session with session_id=conversation_id, attach system_prompt, family memory config, member memory config, sub-agent routing tool IDs
    - Implement get_session() and delete_session()
    - Maintain bijective mapping: conversation_id = session_id without transformation
    - On first message: create new session; on subsequent messages: reuse existing session
    - On conversation delete: delete corresponding runtime session
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6_

  - [x] 11.2 Write property tests for session-conversation bijection
    - **Property 8: Session-Conversation Bijection** — for any conversation, exactly one runtime session exists with session_id == conversation_id; new conversations create sessions, subsequent messages reuse them
    - **Validates: Requirements 1.1, 1.2, 1.6**

  - [x] 11.3 Implement streaming response handling
    - Implement invoke_session(): stream response events back to Flask SSE handler as StreamEvent objects
    - Emit StreamEvent with type restricted to: text_delta, tool_use, message_done, error
    - On streaming complete with text content: persist full assistant message to DynamoDB, emit message_done with conversation_id
    - _Requirements: 1.4, 25.1, 25.2, 25.3_

  - [x] 11.4 Write property tests for streaming event integrity
    - **Property 21: Streaming Event Integrity** — each chunk is a valid StreamEvent with type in {text_delta, tool_use, message_done, error}; text completion persists message and emits message_done
    - **Validates: Requirements 25.1, 25.2, 25.3**

  - [x] 11.5 Implement orchestrator-to-sub-agent routing
    - When orchestrator invokes a routing tool, create sub-agent session via InvokeAgentRuntime API with template system_prompt and sub-agent domain tools
    - Pass context.session_id between orchestrator and sub-agent containers
    - Sub-agent returns response to orchestrator for inclusion in user-facing stream
    - Sub-agent receives only its own domain tools (no access to other sub-agents' tools or orchestrator routing tools)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 11.6 Write property tests for orchestrator-to-sub-agent routing
    - **Property 3: Orchestrator-to-Sub-Agent Routing** — orchestrator receives only user's enabled routing tools; sub-agent receives only its domain tools; tool sets are disjoint
    - **Validates: Requirements 2.2, 2.5, 9.3, 9.4, 9.5**

  - [x] 11.7 Implement deployment model support
    - Deploy orchestrator as one AgentCore Runtime managed agent backed by one ECR container
    - Deploy each sub-agent type as separate AgentCore Runtime managed agent with own ECR container
    - Use InvokeAgentRuntime API for orchestrator-to-sub-agent communication
    - Serve all families from single runtime instance per agent type, resolve family-specific behavior at invocation time
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 11.8 Implement runtime error handling
    - Log errors with session_id and agent_id
    - Retry with exponential backoff up to 3 attempts for transient errors
    - Fall back to direct Bedrock model invocation for persistent failures
    - Return user-friendly error via SSE stream with type "error"
    - _Requirements: 20.1, 20.2, 20.3, 20.4_

  - [x] 11.9 Write property tests for runtime error propagation
    - **Property 19: Runtime Error Propagation** — for any runtime error, it is logged with session_id and agent_id, and a user-friendly error event is emitted on SSE stream
    - **Validates: Requirements 20.1, 20.4**

  - [x] 11.10 Implement sub-agent invocation error handling
    - On sub-agent error: orchestrator continues operating, informs user sub-agent is temporarily unavailable
    - Sub-agent tool failures reported to orchestrator (not silent)
    - _Requirements: 21.1, 21.2, 21.3_

  - [x] 11.11 Write property tests for sub-agent resilience
    - **Property 26: Sub-Agent Resilience** — for any sub-agent error, orchestrator continues and informs user; tool failures are reported, not silent
    - **Validates: Requirements 21.1, 21.2, 21.3**

- [x] 12. Checkpoint — Ensure all tests pass, ask the user if questions arise.

- [x] 13. Integration and wiring
  - [x] 13.1 Implement dynamic sub-agent addition/removal
    - Implement add_sub_agent_for_user(): validate template, check authorization, check admin role for cross-user, merge config, register gateway routing tool, create AgentConfig
    - Implement remove_sub_agent_for_user(): check admin role for cross-user, delete AgentConfig, do NOT delete gateway routing tool
    - Ensure next orchestrator session reflects updated tool set
    - _Requirements: 5.1, 5.3, 8.4_

  - [x] 13.2 Write property tests for dynamic sub-agent addition/removal
    - **Property 2: Dynamic Sub-Agent Addition/Removal** — after add, next session includes routing tool; after remove, next session excludes it; gateway tool not deleted on removal
    - **Validates: Requirements 5.1, 5.3, 8.4, 27.2**

  - [x] 13.3 Migrate chat endpoint to AgentCore Runtime
    - Replace stream_agent_chat() with stream_agent_chat_v2() using AgentCoreRuntimeClient
    - Wire: resolve sub-agent tools → build memory config → create/resume session → invoke with streaming → persist message
    - Replace @require_auth with @agentcore_require_auth
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 13.4 Migrate agent management endpoints
    - Wire POST /agents/configs to add_sub_agent_for_user()
    - Wire DELETE /agents/configs/<agent_type> to remove_sub_agent_for_user()
    - Wire PUT /agents/templates/<id>/authorize for member authorization
    - Wire GET /agents/available to get_available_templates()
    - Wire template CRUD endpoints to AgentManagementClient
    - _Requirements: 4.1, 4.3, 4.4, 5.1, 5.2, 5.3, 6.3, 7.1, 7.2, 7.3_

  - [x] 13.5 Implement user migration to Cognito
    - Create migration script: for each user without cognito_sub, create Cognito user with email, update Users table with cognito_sub, add cognito_sub-index GSI
    - Verify user doesn't already have cognito_sub before creating Cognito user
    - Preserve all existing conversations, profiles, and health records
    - _Requirements: 19.1, 19.2, 19.3, 19.4_

  - [x] 13.6 Write property tests for migration data integrity
    - **Property 15: Migration Data Integrity** — after migration, each user's cognito_sub maps to exactly one Cognito user; Users table updated; existing data preserved; no re-migration of already-migrated users
    - **Validates: Requirements 19.1, 19.2, 19.3, 19.4**

  - [x] 13.7 Wire security controls
    - Scope member short-term memory by member_id and session_id
    - Configure IAM authentication for all Gateway-to-MCP-server communication
    - Ensure MCP server endpoints run within VPC (CDK config)
    - Configure short-lived Cognito access tokens (1-hour) with refresh token rotation
    - Verify requesting user belongs to family before allowing family memory access
    - _Requirements: 31.1, 31.2, 31.3, 31.4, 31.6_

  - [x] 13.8 Wire performance optimizations
    - Parallel family + member memory retrieval in CombinedSessionManager
    - JWKS caching with 1-hour TTL in identity middleware
    - Sub-agent tool ID caching with 60s TTL in Agent Management Client
    - _Requirements: 30.1, 30.2, 30.3, 30.4_

- [x] 14. Final checkpoint — Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation across the five migration pillars
- Property tests validate universal correctness properties from the design document
- The design uses Python throughout — all implementations use Python with Flask, boto3, and bedrock-agentcore SDK
- All 31 requirements and 27 correctness properties are covered by the task plan
