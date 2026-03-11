# HomeAgent — System Architecture

## Overview

HomeAgent is a family AI chat application. Family members interact with Claude (via Amazon Bedrock) through a mobile app. The system supports a pluggable agent architecture — an admin can create custom AI agent types, and members can self-service enable agents for their personal assistant.

```
+-----------------+       +-------------------+       +------------------+
|  Mobile Client  | <---> |   Backend API     | <---> |  AWS Services    |
|  (Expo / RN)    |  HTTP |   (Flask / ECS)   |       |  Bedrock, Dynamo |
+-----------------+  SSE  +-------------------+       +------------------+
```

- **Mobile** — Expo React Native app (TypeScript). Runs on iOS/Android via Expo Go.
- **Backend** — Python Flask API on ECS Fargate behind an ALB. Handles auth, chat, conversations, profiles, agents, health records.
- **Web UI** — Static debug console (HTML/CSS/JS) hosted on S3 + CloudFront.
- **Infrastructure** — AWS CDK (Python). VPC, DynamoDB, ECR, ECS, ALB, S3, CloudFront, CodePipeline.

---

## Deployment Architecture

```
                        ┌─────────────────────────────────────────────┐
                        │              AWS Account (us-east-1)        │
                        │                                             │
┌──────────┐            │  ┌──────────────────────────────────────┐   │
│  GitHub  │──webhook──►│  │       CodePipeline (CI/CD)           │   │
│  (main)  │            │  │  Source → Synth → Test → Deploy →    │   │
└──────────┘            │  │  DockerBuild → ECS Update → WebUI    │   │
                        │  └──────────────────────────────────────┘   │
                        │                                             │
                        │  ┌────────────────────────────┐             │
                        │  │         VPC (2 AZs)         │             │
                        │  │                              │             │
                        │  │  ┌─────────────────────┐    │             │
┌──────────┐            │  │  │   Public Subnets     │    │             │
│  Mobile  │──HTTPS────►│  │  │  ┌───────────────┐  │    │             │
│  App     │            │  │  │  │      ALB       │  │    │             │
│(Expo Go) │◄───SSE─────│  │  │  │  (idle: 300s)  │  │    │             │
└──────────┘            │  │  │  └───────┬───────┘  │    │             │
                        │  │  └──────────┼──────────┘    │             │
                        │  │             │                │             │
                        │  │  ┌──────────▼──────────┐    │             │
                        │  │  │  Private Subnets     │    │             │
                        │  │  │  ┌────────────────┐  │    │  ┌───────┐ │
                        │  │  │  │  ECS Fargate    │  │    │  │Bedrock│ │
                        │  │  │  │  (1–4 tasks)    │──┼────┼─►│Claude │ │
                        │  │  │  │  Flask + gunicorn│ │    │  └───────┘ │
                        │  │  │  └────────────────┘  │    │             │
                        │  │  └──────────────────────┘    │             │
                        │  │         │  NAT GW            │             │
                        │  └─────────┼────────────────────┘             │
                        │            │                                  │
                        │  ┌─────────▼──────────┐  ┌──────────┐        │
                        │  │     DynamoDB        │  │   ECR    │        │
                        │  │  (14 tables,        │  │ homeagent│        │
                        │  │   on-demand)        │  │ -backend │        │
                        │  └────────────────────┘  └──────────┘        │
                        │                                              │
                        │  ┌────────────┐  ┌─────────────────┐         │
                        │  │     S3      │  │   CloudFront    │         │
                        │  │ health-docs │  │   (Web UI)      │         │
                        │  └────────────┘  └─────────────────┘         │
                        └─────────────────────────────────────────────┘
```

### Network Layer

| Resource | Details |
|----------|---------|
| VPC | 2 Availability Zones |
| Public Subnets | ALB, NAT Gateway |
| Private Subnets | ECS tasks (no public IPs) |
| NAT Gateway | 1 (single for cost savings) |

### Compute Layer

| Resource | Details |
|----------|---------|
| ECS Cluster | Fargate launch type |
| Task Definition | 512 CPU, 1024 MiB memory |
| Container | `homeagent-backend:latest` from ECR |
| Worker | gunicorn + gevent (async I/O for SSE) |
| Auto-scaling | 1–4 tasks, CPU target 70% |
| ALB | Public, idle timeout 300s for SSE |
| Health Check | `GET /health` every 30s |

### Data Layer

| Table | Key Schema | GSI | Purpose |
|-------|-----------|-----|---------|
| Users | PK: `user_id` | — | User accounts |
| Devices | PK: `device_id` | `device_token-index`, `user_id-index` | Device registration, token lookup |
| InviteCodes | PK: `code` | — | One-time invite codes |
| Conversations | PK: `conversation_id` | `user_conversations-index` (user_id + updated_at) | Chat threads |
| Messages | PK: `conversation_id`, SK: `sort_key` | — | Chat messages, sorted by time |
| MemberProfiles | PK: `user_id` | — | Member display names, roles, preferences |
| AgentConfigs | PK: `user_id`, SK: `agent_type` | — | Per-member agent enable/disable + config |
| AgentTemplates | PK: `template_id` | `agent_type-index` | Dynamic agent type definitions (admin-managed) |
| FamilyRelationships | PK: `user_id`, SK: `related_user_id` | — | Family tree relationships |
| HealthRecords | PK: `user_id`, SK: `record_id` | `record_type-index` | Structured medical records |
| HealthObservations | PK: `user_id`, SK: `observation_id` | `category-index` | AI-extracted health observations |
| HealthAuditLog | PK: `record_id`, SK: `audit_sk` | `user-audit-index` | Health record change audit trail |
| HealthDocuments | PK: `user_id`, SK: `document_id` | — | Health document metadata (files in S3) |
| ChatMedia | PK: `media_id` | — | Chat image metadata, presigned S3 URLs, TTL auto-cleanup |

All tables use on-demand billing (PAY_PER_REQUEST).

### Storage Layer

| Resource | Details |
|----------|---------|
| S3 Bucket | `homeagent-health-documents-{ACCOUNT_ID}` — encrypted, private, lifecycle to IA at 90 days |
| S3 Bucket | Web UI static hosting (CloudFront distribution) |

### AI Layer

| Resource | Details |
|----------|---------|
| Service | Amazon Bedrock |
| Text Model | Claude Opus 4.6 (`us.anthropic.claude-opus-4-6-v1`) |
| Voice Model | Amazon Nova Sonic (`amazon.nova-sonic-v1:0`) |
| Text API | `converse_stream` (streaming) |
| Voice API | `invoke_model_with_bidirectional_stream` (WebSocket) |
| Agent Framework | Strands Agents SDK (sub-agent orchestration) |
| Max Tokens | 4096 |
| Temperature | 0.7 |
| System Prompt | Configurable (default: family assistant persona) |

### Security

| Concern | Implementation |
|---------|---------------|
| Auth | Bearer token per device (`secrets.token_urlsafe(48)`) |
| Token Storage | Expo SecureStore (iOS Keychain / Android Keystore) |
| Role-Based Access | `admin` / `member` roles, decorator-enforced |
| Invite Codes | Single-use, required for registration |
| Container | Non-root user (`appuser`) |
| Network | Tasks in private subnets, ALB in public |
| IAM | Task role scoped to DynamoDB tables + Bedrock invoke + S3 bucket |
| ECR | Lifecycle policy: keep last 10 images |

---

## Agent System Architecture

HomeAgent uses a pluggable sub-agent architecture powered by the Strands Agents SDK.

### How It Works

```
User Message
     │
     ▼
Personal Agent (orchestrator)
     │
     ├─► ask_health_advisor  (built-in, registered factory)
     ├─► ask_meal_planner    (custom, template-based)
     └─► ask_shopping_assistant (custom, template-based)
```

1. **AgentTemplates table** stores all agent type definitions (name, description, system prompt, default config, availability).
2. **Built-in agents** (e.g. `health_advisor`) have Python factories registered via `@register_agent` and are seeded as templates on startup with `is_builtin=True`.
3. **Custom agents** are created by admin via API. They use a generic factory that creates a Strands sub-agent from the template's `system_prompt`.
4. **AgentConfigs table** stores per-member enable/disable state. Admin can toggle agents for members; members can self-service toggle available agents.
5. **Personal agent** (`build_sub_agent_tools()`) assembles the user's enabled sub-agents at chat time — tries the registered factory first, falls back to the generic custom agent factory.

### Agent Access Control

```
Admin creates template → sets available_to ("all" or [user_ids])
     │
     ▼
Member sees agent in "My Agents" → toggles on/off (PUT/DELETE /api/agents/my/<type>)
     │
     ▼
Chat time → personal agent includes enabled sub-agents as @tool functions
```

---

## CI/CD Pipeline

```
GitHub Push (main)
       │
       ▼
┌──────────────┐
│   Source      │  CodeStar Connection to GitHub
└──────┬───────┘
       ▼
┌──────────────┐
│   Synth       │  pip install CDK deps → cdk synth
└──────┬───────┘
       ▼
┌──────────────┐
│ UpdatePipeline│  Self-mutation: pipeline updates its own definition
└──────┬───────┘
       ▼
┌──────────────┐
│ BackendTests  │  DynamoDB Local in Docker → pytest
│  (pre-deploy) │  Blocks deploy if tests fail
└──────┬───────┘
       ▼
┌──────────────┐
│   Deploy      │  CDK deploys: Network → Data → Security → Service → WebUI
└──────┬───────┘
       ▼
┌──────────────┐
│DockerBuildPush│  Build image → Push to ECR → Force new ECS deployment
│ (post-deploy) │  ECS cluster/service names resolved from CloudFormation
└──────────────┘
```

The pipeline is self-mutating: changes to `infra/stacks/pipeline_stack.py` automatically update the pipeline definition on the next run.

---

## Request Flow: Chat Message

```
1. Mobile sends POST /api/chat with Bearer token
2. ALB routes to ECS task (private subnet)
3. Flask @require_auth decorator:
   a. Extract token from Authorization header
   b. Query Devices GSI (device_token-index)
   c. Look up user from Users table
   d. Set g.user_id, g.user_name, g.user_role
4. Chat route:
   a. Create or validate conversation
   b. Store user message in Messages table
   c. Load last 50 messages as context
   d. Route via _get_chat_stream():
      - AGENTCORE_RUNTIME_ARN set → _stream_via_agentcore() (AgentCore Runtime)
      - USE_AGENT_ORCHESTRATOR=true → stream_agent_chat() (local Strands)
      - Neither → stream_chat() (direct Bedrock converse_stream)
5. SSE streaming response:
   a. Yield text_delta events as tokens arrive
   b. Yield message_done with token counts
   c. Store assistant message in Messages table
6. Mobile SSE client:
   a. Parse data: lines from stream
   b. Append text_delta content to UI in real-time
   c. On message_done, finalize conversation state
```

---

## Request Flow: Voice Mode

```
1. Mobile opens WebSocket to /api/voice?token=<token>&conversation_id=<id>
2. ALB upgrades HTTP → WebSocket (idle timeout 300s, sticky sessions enabled)
3. Flask-sock routes to voice_ws handler
4. _authenticate_ws verifies device token
5. VoiceSession.start() opens bidirectional stream to Nova Sonic
6. Greenlet spawned: reads from Nova Sonic → forwards to client
7. Main loop: reads from client WebSocket → forwards audio to Nova Sonic
8. Audio chunks: base64-encoded PCM 16-bit 16kHz mono
9. Transcripts saved to Messages table when conversation_id provided
10. On disconnect: session.end() closes Nova Sonic stream
```

---

## Request Flow: Image Upload

```
1. Mobile calls POST /api/chat/upload-image with content_type and file_size
2. Backend validates content type and size, creates ChatMedia record
3. Backend generates S3 presigned PUT URL (300s expiry)
4. Mobile uploads image directly to S3 via presigned URL
5. Mobile sends POST /api/chat with media_ids referencing uploaded images
6. Backend fetches images from S3, builds mixed content blocks
7. Bedrock receives image+text content blocks via converse_stream
8. ChatMedia records auto-expire via DynamoDB TTL
```

---

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Mobile | Expo (React Native) | SDK 52, RN 0.76 |
| Mobile Language | TypeScript | 5.7 |
| Navigation | React Navigation | 7.0 |
| Secure Storage | expo-secure-store | 14.0 |
| Audio Recording/Playback | expo-av | 16.0 |
| Image Picker | expo-image-picker | — |
| Backend | Flask | 3.1 |
| WebSocket | flask-sock | 0.7+ |
| WSGI Server | gunicorn + gevent | 23.0 / 24.11 |
| AI (Text) | Amazon Bedrock | Claude Opus 4.6 |
| AI (Voice) | Amazon Bedrock | Nova Sonic v1 |
| Agent Framework | Strands Agents SDK | — |
| Database | Amazon DynamoDB | On-demand (14 tables) |
| Object Storage | Amazon S3 | Health documents + chat media |
| Container | Docker | python:3.12-slim |
| Orchestration | ECS Fargate | — |
| Load Balancer | Application LB | WebSocket + HTTP |
| CDN | Amazon CloudFront | Web UI |
| Infrastructure | AWS CDK | 2.177 |
| CI/CD | AWS CodePipeline | CDK Pipelines |
| Source Control | GitHub | CodeStar Connection |
| Container Registry | Amazon ECR | — |
