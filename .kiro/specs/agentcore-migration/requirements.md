# Requirements Document

## Introduction

This document defines the requirements for migrating the HomeAgent family agent platform from its current custom agent orchestration (Strands Agents, DynamoDB-based conversations, device-token auth) to Amazon Bedrock AgentCore. The migration covers five pillars: **AgentCore Runtime** for the orchestrator agent and sub-agent session management via separate ECR containers, **AgentCore Agent Management** for sub-agent template definitions, per-user configurations, authorization via the available_to field, and dynamic addition/removal by family owners, **AgentCore Memory** for dual-tier memory (family long-term by family_id with no TTL, and member short-term by member_id with 30-day TTL), **AgentCore Gateway** for two-level tool management (orchestrator routing tools and sub-agent domain tools via MCP servers), and **AgentCore Identity** for Cognito JWT-based authentication replacing device-token auth with role-based access control. The existing REST+SSE API surface and mobile/web frontends remain unchanged; only backend internals and infrastructure stacks change.

## Glossary

- **AgentCore_Runtime_Client**: The component that manages orchestrator and sub-agent sessions via the AgentCore Runtime API, replacing in-process Strands Agent instantiation
- **Agent_Management_Client**: The component that manages agent templates (CRUD), per-user agent configs, authorization checks, and dynamic sub-agent resolution, replacing agent_config.py and agent_template.py
- **AgentCore_Gateway_Manager**: The component that registers and manages tools at two levels (orchestrator routing tools and sub-agent domain tools) via the AgentCore Gateway API
- **AgentCore_Memory_Manager**: The component that manages dual-tier memory stores (family long-term and member short-term) via the AgentCore Memory API
- **AgentCore_Identity_Middleware**: The Flask middleware that validates Cognito JWT tokens and resolves user identity, replacing device-token auth
- **CombinedSessionManager**: The object that merges both memory tiers into a single configuration for agent runtime sessions
- **AgentTemplate**: A definition of a sub-agent type including template_id, agent_type, name, description, system_prompt, tool_server_ids, default_config, available_to, is_builtin flag, and created_by field
- **AgentConfig**: A per-user record keyed by (user_id, agent_type) that enables or disables a specific sub-agent type for that user, with optional config overrides and a resolved gateway_tool_id
- **Orchestrator_Agent**: The personal agent runtime deployed as an ECR container that receives user messages and routes them to sub-agents via routing tool calls
- **Sub_Agent**: A domain-specific agent (built-in or custom) deployed as a separate ECR container, invoked by the orchestrator via the InvokeAgentRuntime_API
- **Routing_Tool**: An orchestrator-level tool (e.g., ask_health_advisor) that invokes a sub-agent runtime
- **Domain_Tool**: A sub-agent-level tool provided by an MCP_Server (e.g., get_family_health_records)
- **Family_Long_Term_Memory**: The AgentCore Memory store scoped by family_id that persists health knowledge, family preferences, and shared context indefinitely (no TTL)
- **Member_Short_Term_Memory**: The AgentCore Memory store scoped by member_id and session_id that tracks per-conversation context with a 30-day TTL
- **IdentityContext**: The object containing user_id, family_id, role, and cognito_sub extracted from a validated JWT
- **MCP_Server**: A Model Context Protocol server endpoint registered in AgentCore Gateway that exposes Domain_Tools to sub-agent runtimes, authenticated via IAM
- **FamilyGroups_Table**: The DynamoDB table mapping users to family groups for memory scoping, with a member-family-index GSI
- **Cognito_User_Pool**: The Amazon Cognito user pool used for user authentication and JWT issuance, with custom attributes for family_id and app_role
- **StreamEvent**: A server-sent event chunk emitted during agent response streaming with type restricted to text_delta, tool_use, message_done, or error
- **ECR_Container**: An Elastic Container Registry container image; each agent type (orchestrator, sub-agents) is deployed as a separate ECR container in AgentCore Runtime
- **InvokeAgentRuntime_API**: The AgentCore Runtime API used for orchestrator-to-sub-agent communication between separate container runtimes
- **SubAgentToolConfig**: A runtime resolution object containing agent_type, tool_name, description, sub_agent_runtime_id, system_prompt, tool_server_ids, and user_config

## Requirements

### Requirement 1: Orchestrator Runtime Session Management

**User Story:** As a backend developer, I want to replace in-process Strands Agent instantiation with an AgentCore Runtime managed orchestrator agent, so that the personal agent lifecycle is handled by a managed service and each conversation maps to a dedicated runtime session.

#### Acceptance Criteria

1. WHEN a user sends the first message in a new conversation, THE AgentCore_Runtime_Client SHALL create a new orchestrator runtime session with session_id equal to the conversation_id
2. WHEN a user sends a subsequent message in an existing conversation, THE AgentCore_Runtime_Client SHALL reuse the existing orchestrator runtime session identified by the conversation_id
3. WHEN creating an orchestrator session, THE AgentCore_Runtime_Client SHALL attach the personalized system prompt, family memory configuration, member memory configuration, and the user's authorized sub-agent Routing_Tool IDs to the session
4. WHEN invoking an orchestrator session, THE AgentCore_Runtime_Client SHALL stream response events back to the Flask SSE handler as StreamEvent objects
5. WHEN a conversation is deleted, THE AgentCore_Runtime_Client SHALL delete the corresponding orchestrator runtime session
6. THE AgentCore_Runtime_Client SHALL maintain a bijective mapping where each conversation_id corresponds to exactly one AgentCore Runtime session_id, using the conversation_id as the session_id without transformation

### Requirement 2: Orchestrator-to-Sub-Agent Routing

**User Story:** As a backend developer, I want the orchestrator agent to route user queries to the appropriate sub-agent via tool calls, so that domain-specific agents handle specialized requests while the orchestrator manages the overall conversation.

#### Acceptance Criteria

1. WHEN the orchestrator agent determines a query should be handled by a sub-agent, THE Orchestrator_Agent SHALL invoke the corresponding Routing_Tool (e.g., ask_health_advisor) to delegate the query
2. WHEN a Routing_Tool is invoked, THE AgentCore_Runtime_Client SHALL create a sub-agent session using the InvokeAgentRuntime_API with the template-defined system_prompt and the sub-agent's Domain_Tools
3. WHEN a sub-agent completes its response, THE Sub_Agent SHALL return the response to the Orchestrator_Agent for inclusion in the user-facing stream
4. THE Orchestrator_Agent SHALL receive only Routing_Tools corresponding to the user's enabled and authorized sub-agents in its tool set
5. WHEN the orchestrator invokes a sub-agent, THE Sub_Agent SHALL receive only its own Domain_Tools and SHALL NOT have access to other sub-agents' tools or the orchestrator's Routing_Tools
6. WHEN the orchestrator invokes a sub-agent, THE AgentCore_Runtime_Client SHALL pass context.session_id between the orchestrator container and the sub-agent container for session context management

### Requirement 3: Deployment Model

**User Story:** As a DevOps engineer, I want each agent type deployed as a separate ECR container in AgentCore Runtime, so that agents are independently scalable and deployable.

#### Acceptance Criteria

1. THE system SHALL deploy the orchestrator agent (personal agent) as one AgentCore Runtime managed agent backed by one ECR_Container
2. THE system SHALL deploy each sub-agent type (health_advisor, custom agents) as a separate AgentCore Runtime managed agent backed by its own ECR_Container
3. WHEN the orchestrator invokes a sub-agent, THE AgentCore_Runtime_Client SHALL use the InvokeAgentRuntime_API to communicate between the orchestrator container and the sub-agent container
4. THE system SHALL manage session context via context.session_id passed between orchestrator and sub-agent runtimes
5. THE system SHALL serve all families from a single runtime instance per agent type, resolving family-specific behavior at invocation time based on the session's family_id and user_id context

### Requirement 4: Agent Template Management

**User Story:** As a family owner, I want to manage sub-agent templates that define available agent types, so that I can customize which agent capabilities are available to my family.

#### Acceptance Criteria

1. WHEN an admin creates a new AgentTemplate, THE Agent_Management_Client SHALL store the template with a unique template_id, agent_type slug, name, description, system_prompt, tool_server_ids, default_config, available_to, is_builtin flag, created_by field, created_at, and updated_at timestamps
2. THE Agent_Management_Client SHALL enforce that agent_type is unique across all templates
3. WHEN an admin updates an AgentTemplate, THE Agent_Management_Client SHALL persist the changes and apply the updated configuration to future sessions
4. WHEN an admin deletes a non-builtin AgentTemplate, THE Agent_Management_Client SHALL delete the template and cascade-delete all AgentConfigs referencing that template's agent_type
5. WHEN an admin attempts to delete a built-in AgentTemplate (is_builtin == True), THE Agent_Management_Client SHALL reject the deletion
6. THE Agent_Management_Client SHALL seed built-in templates (health_advisor, logistics_assistant, shopping_assistant) on startup with is_builtin == True and created_by == "system"
7. WHEN listing templates, THE Agent_Management_Client SHALL return all templates for admin users and only authorized templates for non-admin users via the get_available_templates method

### Requirement 5: Per-User Agent Configuration

**User Story:** As a family owner, I want to enable or disable specific sub-agents for each family member, so that each person's personal agent has the right set of capabilities.

#### Acceptance Criteria

1. WHEN a user enables a sub-agent, THE Agent_Management_Client SHALL create an AgentConfig record with user_id, agent_type, enabled=True, and merged config (template defaults + user overrides)
2. WHEN a user disables a sub-agent, THE Agent_Management_Client SHALL update the AgentConfig record to set enabled=False
3. WHEN a user removes a sub-agent, THE Agent_Management_Client SHALL delete the AgentConfig record for that user_id and agent_type
4. WHEN creating an AgentConfig, THE Agent_Management_Client SHALL verify that the agent_type references a valid AgentTemplate
5. WHEN creating an AgentConfig, THE Agent_Management_Client SHALL verify that the user is authorized for the template by checking the available_to field before allowing the configuration
6. WHEN creating an AgentConfig, THE Agent_Management_Client SHALL merge the user-provided config with the template's default_config, with user overrides taking precedence
7. THE Agent_Management_Client SHALL store the resolved gateway_tool_id on the AgentConfig record for orchestrator routing

### Requirement 6: Template Authorization Enforcement

**User Story:** As a family owner, I want to control which family members can access each sub-agent type via the available_to field, so that sensitive agent capabilities are restricted to authorized members.

#### Acceptance Criteria

1. WHEN an AgentTemplate has available_to set to "all", THE Agent_Management_Client SHALL authorize every user to enable and use that sub-agent
2. WHEN an AgentTemplate has available_to set to a list of user_ids, THE Agent_Management_Client SHALL authorize only those user_ids to enable and use that sub-agent
3. WHEN the available_to field is updated to remove a user_id, THE Agent_Management_Client SHALL exclude that user's Routing_Tool from future orchestrator sessions without deleting the existing AgentConfig
4. THE Agent_Management_Client SHALL validate that available_to is either the string "all" or a non-empty list of valid user_ids
5. THE Agent_Management_Client SHALL check authorization both at AgentConfig creation time and at session tool resolution time

### Requirement 7: Admin-Only Cross-User Configuration

**User Story:** As a family owner with admin role, I want to manage sub-agent configurations for other family members, so that I can set up appropriate agent capabilities for children or other members.

#### Acceptance Criteria

1. WHEN a requesting user adds or removes a sub-agent config for a different target user, THE Agent_Management_Client SHALL verify that the requesting user has role "admin"
2. IF a non-admin user attempts to modify another user's agent config, THEN THE Agent_Management_Client SHALL reject the request with HTTP 403
3. WHEN a user modifies their own agent config, THE Agent_Management_Client SHALL allow the operation regardless of role, provided the user is authorized for the template

### Requirement 8: Sub-Agent Tool Resolution

**User Story:** As a backend developer, I want the system to dynamically resolve which sub-agent routing tools are available for each user's orchestrator session, so that the orchestrator only sees tools for enabled and authorized sub-agents.

#### Acceptance Criteria

1. WHEN resolving sub-agent tools for a user, THE Agent_Management_Client SHALL return Gateway tool IDs only for AgentConfigs where enabled == True AND the user is authorized for the corresponding template
2. WHEN resolving sub-agent tools, THE Agent_Management_Client SHALL exclude agents with missing templates and log a warning
3. THE Agent_Management_Client SHALL return the resolved tool IDs sorted by agent_type for deterministic ordering
4. WHEN a sub-agent is added or removed for a user, THE Agent_Management_Client SHALL ensure the next orchestrator session reflects the updated tool set

### Requirement 9: Two-Level Gateway Tool Architecture

**User Story:** As a backend developer, I want tools managed at two levels in AgentCore Gateway (orchestrator routing tools and sub-agent domain tools), so that the orchestrator routes to sub-agents and each sub-agent has its own domain-specific tools.

#### Acceptance Criteria

1. THE AgentCore_Gateway_Manager SHALL register orchestrator-level Routing_Tools where each enabled sub-agent type becomes a tool (e.g., ask_health_advisor, ask_shopping_assistant) that the orchestrator can invoke
2. THE AgentCore_Gateway_Manager SHALL register sub-agent-level Domain_Tools as MCP_Server endpoints for each sub-agent type (e.g., health tools MCP, family tools MCP)
3. WHEN resolving tools for an orchestrator session, THE AgentCore_Gateway_Manager SHALL return only Routing_Tools for the user's enabled sub-agents
4. WHEN resolving tools for a sub-agent session, THE AgentCore_Gateway_Manager SHALL return only the Domain_Tools assigned to that sub-agent's agent_type
5. THE AgentCore_Gateway_Manager SHALL maintain disjoint tool sets between the orchestrator level and each sub-agent level

### Requirement 10: Built-in Agent Tool Registration

**User Story:** As a backend developer, I want built-in agents (health_advisor) to have their specific MCP tools registered in the Gateway, so that domain-specific tools are centrally managed rather than defined in Python code.

#### Acceptance Criteria

1. THE AgentCore_Gateway_Manager SHALL register health tools (get_family_health_records, get_health_summary, save_health_observation, get_health_observations, get_family_health_context, search_health_conversations) as MCP_Server endpoints for the health_advisor sub-agent
2. THE AgentCore_Gateway_Manager SHALL register family tree tools as MCP_Server endpoints
3. WHEN registering an MCP_Server, THE AgentCore_Gateway_Manager SHALL configure IAM-based authentication for server-to-server communication
4. THE AgentCore_Gateway_Manager SHALL support dynamic tool registration when new templates are created

### Requirement 11: Built-in vs Custom Agent Handling

**User Story:** As a backend developer, I want both built-in and custom agents to follow the same authorization, configuration, and routing paths, so that the architecture is consistent regardless of agent origin.

#### Acceptance Criteria

1. THE Agent_Management_Client SHALL route both built-in agents (is_builtin == True) and custom agents (is_builtin == False) through the same authorization, configuration, and orchestrator routing paths
2. WHEN a built-in agent is invoked, THE Sub_Agent SHALL receive its pre-registered MCP_Server Domain_Tools in addition to its system_prompt
3. WHEN a custom agent is invoked, THE Sub_Agent SHALL use its template-defined system_prompt as the primary behavior driver, with optional generic MCP tools or no tools
4. THE AgentCore_Gateway_Manager SHALL represent both built-in and custom agents as Routing_Tools at the orchestrator level

### Requirement 12: Dual-Tier Memory Configuration

**User Story:** As a backend developer, I want to split the single memory store into family-scoped long-term and member-scoped short-term memories, so that health knowledge persists across the family while conversation context remains per-member.

#### Acceptance Criteria

1. WHEN creating a CombinedSessionManager, THE AgentCore_Memory_Manager SHALL configure the family memory store with family_id as the actor_id
2. WHEN creating a CombinedSessionManager, THE AgentCore_Memory_Manager SHALL configure the member memory store with member_id as the actor_id
3. THE AgentCore_Memory_Manager SHALL configure family memory retrieval namespaces as `/family/{actorId}/health` and `/family/{actorId}/preferences`
4. THE AgentCore_Memory_Manager SHALL configure member memory retrieval namespaces as `/member/{actorId}/context` and `/member/{actorId}/summaries/{sessionId}`
5. WHEN creating a CombinedSessionManager, THE AgentCore_Memory_Manager SHALL verify that the member_id belongs to the family identified by family_id

### Requirement 13: Memory Tier Isolation

**User Story:** As a security engineer, I want family long-term memory and member short-term memory to be strictly isolated, so that cross-tier data leakage is prevented.

#### Acceptance Criteria

1. THE AgentCore_Memory_Manager SHALL store family long-term memory records in a separate AgentCore Memory store from member short-term memory records
2. WHEN querying family long-term memory by family_id, THE AgentCore_Memory_Manager SHALL return only records from the family memory store
3. WHEN querying member short-term memory by member_id, THE AgentCore_Memory_Manager SHALL return only records from the member memory store
4. THE AgentCore_Memory_Manager SHALL use distinct memory store IDs for the family and member memory stores

### Requirement 14: Family Memory Persistence and Access

**User Story:** As a family member, I want family health knowledge to persist indefinitely and be accessible to all family members, so that shared health context is always available.

#### Acceptance Criteria

1. WHEN storing a record in Family_Long_Term_Memory, THE AgentCore_Memory_Manager SHALL store the record without a TTL
2. WHEN a family member queries Family_Long_Term_Memory, THE AgentCore_Memory_Manager SHALL return records for the family_id associated with that member
3. THE AgentCore_Memory_Manager SHALL validate that the category field of family memory records is one of: health, preferences, context
4. THE AgentCore_Memory_Manager SHALL enforce a maximum content length of 10,000 characters for family memory records
5. THE AgentCore_Memory_Manager SHALL store the memory_key in hierarchical format: {category}/{subcategory}/{identifier}

### Requirement 15: Member Memory Expiry

**User Story:** As a system architect, I want member short-term memory to expire after 30 days, so that per-conversation context does not accumulate indefinitely.

#### Acceptance Criteria

1. WHEN storing a record in Member_Short_Term_Memory, THE AgentCore_Memory_Manager SHALL set a TTL of 30 days from the creation timestamp
2. THE AgentCore_Memory_Manager SHALL scope member short-term memory records by both member_id and session_id
3. WHEN a session interaction occurs, THE AgentCore_Memory_Manager SHALL increment the message_count for the corresponding member memory record

### Requirement 16: Family Scope Correctness

**User Story:** As a family member, I want my memory retrieval to include all family-level records for my family and only my own member-level records, so that I see shared family context without accessing other members' private conversations.

#### Acceptance Criteria

1. WHEN retrieving memory for a user, THE CombinedSessionManager SHALL include all family-level records matching the user's family_id
2. WHEN retrieving memory for a user, THE CombinedSessionManager SHALL include only member-level records matching the user's own member_id
3. WHEN retrieving memory for a user, THE CombinedSessionManager SHALL exclude member-level records belonging to other members of the same family

### Requirement 17: Cognito JWT Authentication

**User Story:** As a backend developer, I want to replace device-token authentication with Cognito JWT validation via AgentCore Identity, so that authentication uses industry-standard tokens with proper signing and expiration.

#### Acceptance Criteria

1. WHEN a request includes a valid Bearer JWT in the Authorization header, THE AgentCore_Identity_Middleware SHALL validate the token against the configured Cognito_User_Pool
2. WHEN a token is valid, THE AgentCore_Identity_Middleware SHALL extract the cognito_sub and resolve the corresponding application user_id, family_id, and role
3. WHEN a token is valid, THE AgentCore_Identity_Middleware SHALL set g.user_id, g.family_id, g.user_role, and g.cognito_sub on the Flask request context
4. WHEN a request is missing the Authorization header or the header does not start with "Bearer ", THE AgentCore_Identity_Middleware SHALL return HTTP 401 with an error message
5. WHEN a token is expired, THE AgentCore_Identity_Middleware SHALL return HTTP 401 with error code TOKEN_EXPIRED
6. WHEN a token is malformed or issued by an unknown provider, THE AgentCore_Identity_Middleware SHALL return HTTP 401 with an error message
7. WHEN a valid token's cognito_sub does not map to any application user, THE AgentCore_Identity_Middleware SHALL return HTTP 401 with "User not registered" error

### Requirement 18: Role-Based Access Control

**User Story:** As a system administrator, I want role-based access control enforced via Cognito custom attributes, so that only authorized users can perform privileged operations.

#### Acceptance Criteria

1. THE AgentCore_Identity_Middleware SHALL support role values of admin and member
2. WHEN a route is decorated with a role requirement, THE AgentCore_Identity_Middleware SHALL return HTTP 403 if the authenticated user's role does not match the required role
3. THE Cognito_User_Pool SHALL store family_id and app_role as custom attributes settable only by admin operations

### Requirement 19: User Migration to Cognito

**User Story:** As a system administrator, I want to migrate existing device-token users to Cognito, so that all users authenticate via the new identity system without losing access to their data.

#### Acceptance Criteria

1. WHEN migrating a user, THE migration process SHALL create a Cognito user with the user's email address
2. WHEN migrating a user, THE migration process SHALL update the Users table with the cognito_sub field and add a cognito_sub-index GSI for token-to-user lookup
3. WHEN migrating a user, THE migration process SHALL preserve all existing conversations, profiles, and health records
4. WHEN migrating a user, THE migration process SHALL verify that the user does not already have a cognito_sub before creating a new Cognito user
5. WHILE the migration is in progress, THE AgentCore_Identity_Middleware SHALL support both device-token and Cognito JWT authentication (dual-auth mode)

### Requirement 20: Runtime Error Handling

**User Story:** As a user, I want the system to handle agent runtime failures gracefully, so that I receive a clear error message and the system recovers without data loss.

#### Acceptance Criteria

1. IF the AgentCore Runtime returns an error when creating or invoking a session, THEN THE AgentCore_Runtime_Client SHALL log the error with session_id and agent_id
2. IF a transient runtime error occurs, THEN THE AgentCore_Runtime_Client SHALL retry with exponential backoff up to 3 attempts
3. IF a persistent runtime failure occurs after retries, THEN THE AgentCore_Runtime_Client SHALL fall back to direct Bedrock model invocation without managed sessions
4. IF a runtime error occurs, THEN THE AgentCore_Runtime_Client SHALL return a user-friendly error via SSE stream with type "error"

### Requirement 21: Sub-Agent Invocation Error Handling

**User Story:** As a user, I want the system to handle sub-agent failures gracefully, so that the orchestrator can inform me when a specific sub-agent is unavailable rather than crashing the entire session.

#### Acceptance Criteria

1. IF a Sub_Agent returns an error during invocation, THEN THE Orchestrator_Agent SHALL receive the error and continue operating without crashing the session
2. WHEN a sub-agent error is received, THE Orchestrator_Agent SHALL inform the user that the specific sub-agent is temporarily unavailable
3. IF a sub-agent tool execution fails, THEN THE Sub_Agent SHALL report the tool error to the orchestrator rather than failing silently

### Requirement 22: Memory Service Error Handling

**User Story:** As a user, I want the system to continue functioning when memory services are unavailable, so that I can still get agent responses even without historical context.

#### Acceptance Criteria

1. IF the AgentCore Memory service is unreachable during retrieval, THEN THE AgentCore_Memory_Manager SHALL log a warning and proceed without memory context
2. IF the AgentCore Memory service is unreachable during storage, THEN THE AgentCore_Memory_Manager SHALL queue the failed store operation for background retry
3. WHILE the memory service is unavailable, THE AgentCore_Runtime_Client SHALL operate in stateless mode and continue providing agent responses

### Requirement 23: Gateway Tool Failure Handling

**User Story:** As a user, I want the system to handle tool execution failures gracefully, so that the agent can inform me when a tool is unavailable rather than failing silently.

#### Acceptance Criteria

1. IF an MCP_Server endpoint is unreachable during tool execution, THEN THE AgentCore_Gateway_Manager SHALL report the tool error to the agent runtime
2. WHEN a tool error is reported, THE AgentCore_Runtime_Client SHALL allow the agent LLM to handle the error and communicate tool unavailability to the user
3. THE AgentCore_Gateway_Manager SHALL implement health checks on registered MCP_Servers and temporarily remove unhealthy servers from tool resolution

### Requirement 24: Family Group Resolution

**User Story:** As a user, I want the system to handle missing family group assignments gracefully, so that I can still use the system even if I am not yet assigned to a family.

#### Acceptance Criteria

1. IF an authenticated user has no family_id mapping in the FamilyGroups_Table, THEN THE AgentCore_Identity_Middleware SHALL proceed with member-only memory and log a warning
2. IF a user without a family group logs in for the first time, THEN THE system SHALL auto-create a single-member family group for that user

### Requirement 25: Streaming Response Handling

**User Story:** As a user, I want to receive agent responses as a real-time stream, so that I see partial responses as they are generated rather than waiting for the full response.

#### Acceptance Criteria

1. WHEN the orchestrator agent runtime produces response chunks, THE AgentCore_Runtime_Client SHALL forward each chunk as a StreamEvent to the Flask SSE handler
2. THE AgentCore_Runtime_Client SHALL emit StreamEvent objects with type values limited to: text_delta, tool_use, message_done, error
3. WHEN streaming completes with text content, THE system SHALL persist the full assistant message to DynamoDB and emit a message_done event with the conversation_id

### Requirement 26: Tool Parity

**User Story:** As a product owner, I want all tools available in the current Strands Agent system to produce equivalent results when invoked through AgentCore Gateway, so that the migration does not degrade functionality.

#### Acceptance Criteria

1. THE AgentCore_Gateway_Manager SHALL register every tool currently available in the Strands Agent system in AgentCore Gateway
2. WHEN a tool is invoked through the Gateway MCP protocol, THE MCP_Server SHALL produce results equivalent to the same tool invoked directly in the current system
3. THE AgentCore_Gateway_Manager SHALL support tool versioning and updates via the Gateway API

### Requirement 27: Template Deletion Cascade

**User Story:** As a backend developer, I want template deletion to cascade-delete all dependent agent configs, so that orphaned configs do not cause errors during sub-agent resolution.

#### Acceptance Criteria

1. WHEN a non-builtin AgentTemplate is deleted, THE Agent_Management_Client SHALL delete all AgentConfig records that reference the deleted template's agent_type
2. WHEN a template is deleted, THE Agent_Management_Client SHALL NOT delete the corresponding Gateway Routing_Tool (other users may still reference it until cleanup)
3. WHEN resolving sub-agent tools, THE Agent_Management_Client SHALL skip AgentConfigs whose referenced template no longer exists and log a warning

### Requirement 28: Built-in Template Seeding

**User Story:** As a backend developer, I want built-in agent templates to be automatically seeded on application startup, so that core agent capabilities are always available without manual configuration.

#### Acceptance Criteria

1. WHEN the application starts, THE Agent_Management_Client SHALL check for the existence of built-in templates (health_advisor, logistics_assistant, shopping_assistant)
2. WHEN a built-in template does not exist, THE Agent_Management_Client SHALL create it with the predefined system_prompt, tool_server_ids, and available_to set to "all"
3. WHEN a built-in template already exists, THE Agent_Management_Client SHALL not overwrite it
4. THE Agent_Management_Client SHALL mark seeded templates with is_builtin == True and created_by == "system"

### Requirement 29: Infrastructure and Configuration

**User Story:** As a DevOps engineer, I want all new AgentCore resources provisioned via CDK, so that infrastructure is reproducible and version-controlled.

#### Acceptance Criteria

1. THE CDK stack SHALL provision a Cognito_User_Pool with email sign-in, custom attributes (family_id, app_role), and self-sign-up disabled
2. THE CDK stack SHALL provision DynamoDB tables for FamilyMemories, MemberMemories, and FamilyGroups with the schemas defined in the design document
3. THE system SHALL read all AgentCore configuration (agent_id, memory store IDs, gateway ID, Cognito pool ID, Cognito client ID) from environment variables
4. THE FamilyMemories table SHALL include global secondary indexes for category-based (family_id + category) and update-time-based (family_id + updated_at) queries
5. THE MemberMemories table SHALL include a global secondary index for creation-time-based (member_id + created_at) queries
6. THE FamilyGroups table SHALL include a global secondary index (member-family-index) for looking up a member's family_id by member_id
7. THE CDK stack SHALL provision DynamoDB tables with PAY_PER_REQUEST billing mode

### Requirement 30: Performance

**User Story:** As a user, I want the system to respond quickly despite the additional managed service layers, so that the migration does not noticeably degrade response times.

#### Acceptance Criteria

1. THE AgentCore_Memory_Manager SHALL execute family and member memory retrievals in parallel to keep combined retrieval latency under 200ms
2. THE AgentCore_Identity_Middleware SHALL cache the Cognito JWKS locally with a 1-hour TTL to avoid per-request calls to Cognito
3. THE AgentCore_Runtime_Client SHALL keep ECS tasks in the same AWS region as the AgentCore Runtime service to minimize network latency
4. THE Agent_Management_Client SHALL cache resolved sub-agent tool IDs per user with a short TTL (60s) to avoid repeated lookups within rapid message sequences

### Requirement 31: Data Isolation and Security

**User Story:** As a security engineer, I want strict data isolation between family members' private data and proper authentication for all service-to-service communication, so that the system meets security best practices.

#### Acceptance Criteria

1. THE AgentCore_Memory_Manager SHALL scope member short-term memory by both member_id and session_id, preventing any member from accessing another member's short-term memory
2. THE AgentCore_Gateway_Manager SHALL use IAM authentication for all Gateway-to-MCP-server communication
3. THE MCP_Server endpoints SHALL run within the VPC and not be publicly accessible
4. THE Cognito_User_Pool SHALL issue short-lived access tokens (1-hour expiry) with refresh token rotation
5. WHILE dual-auth mode is active, THE AgentCore_Identity_Middleware SHALL accept both device tokens and Cognito JWTs, and deprecate device tokens after all users are migrated
6. THE AgentCore_Identity_Middleware SHALL verify the requesting user belongs to the family before allowing family memory access, blocking cross-family access at the application layer
