# HomeAgent: Family AI Agent Platform

A mobile-first platform where family members chat with Claude (via Amazon Bedrock) through a shared family workspace. HomeAgent combines real-time AI chat, voice interaction, health management, and a pluggable agent system into a single family-oriented app. Members can have text conversations with streaming responses, attach images, use voice-to-chat with automatic transcription, or speak directly in real-time voice mode powered by Amazon Nova Sonic. An extensible agent framework lets admins deploy specialized sub-agents (health advisor, logistics assistant, shopping assistant) with granular per-member authorization and data permissions. Amazon Bedrock AgentCore provides runtime orchestration, persistent memory, MCP tool gateway, and identity management.

---

## Table of Contents

- [App Design and Features](#app-design-and-features)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Deployment](#deployment)
- [Environment Variables](#environment-variables)
- [API Overview](#api-overview)
- [Documentation](#documentation)

---

## App Design and Features

### Text Chat

Real-time streaming chat with Claude via Amazon Bedrock's `converse_stream` API. Responses are delivered over Server-Sent Events (SSE), providing a token-by-token streaming experience in the mobile app. Conversations are persisted in DynamoDB with automatic title generation. Multi-turn conversation history is maintained and injected into each request so Claude has full context. The system prompt and model ID are configurable via environment variables.

### Image Attachments

Users can attach up to 5 images per message. The upload pipeline uses S3 presigned PUT URLs -- the client requests a presigned URL from the backend, uploads the image directly to S3, and then sends the message with media references. Supported formats include JPEG, PNG, GIF, and WebP. Images are passed to Claude as multimodal content blocks alongside the text message.

### Voice-to-Chat

An inline microphone button in the chat input lets users tap to record and tap again to stop. The recorded audio (WAV format) is uploaded to S3 via the same presigned URL pipeline used for images. The backend transcribes the audio server-side using AWS Transcribe with automatic language detection supporting English (en-US) and Chinese (zh-CN). The transcribed text is then sent to Claude as a regular text message. Maximum audio upload size is 25 MB.

### Voice Mode

A dedicated full-screen voice interface provides bidirectional WebSocket audio streaming powered by Amazon Nova Sonic. Users speak naturally and receive spoken responses in real time, creating a speech-to-speech conversational experience. The voice session is managed over a WebSocket connection at `/api/voice`.

### Agent System

A pluggable sub-agent architecture built on the Strands Agents SDK. Agents are registered via a decorator-based factory pattern and attached as tools to the main orchestrator agent.

**Built-in agents:**

| Agent | Description | Required Permissions |
|-------|-------------|---------------------|
| Health Advisor | Family health companion with access to medical records, health observations, and conversation history. Provides age-specific guidance and personalized wellness recommendations. | `health_data`, `medical_records` |
| Logistics Assistant | Email drafting and scheduling assistance for family coordination. | `email_access`, `calendar_access` |
| Shopping Assistant | Product search and recommendations. | None |

**Custom agents:** Admins can create new agent types at runtime by defining templates with custom system prompts, descriptions, and configuration. Templates are stored in DynamoDB and dynamically loaded.

**2-layer authorization model:**
1. **Admin authorization** -- The family admin authorizes which agents are available to each member (`available_to` controls on templates).
2. **Member self-service** -- Members can enable or disable authorized agents from their own agent settings screen.

### AgentCore Integration

The backend integrates with Amazon Bedrock AgentCore for production-grade agent infrastructure:

- **Runtime** — Serverless agent orchestration. The orchestrator agent is deployed to AgentCore Runtime and invoked via the Runtime API, providing automatic scaling and session management.
- **Memory** — Persistent memory stores for both family-level shared context and per-member personal context. Memories are stored and retrieved via the AgentCore Memory API, enabling agents to recall past interactions and preferences.
- **Gateway** — MCP (Model Context Protocol) tool gateway that routes tool calls to health and family tree MCP servers. Agents can invoke tools through the gateway without direct endpoint management.
- **Identity** — Cognito User Pool provisioned by the AgentCore stack provides JWT-based authentication. The backend validates Cognito tokens and maps them to internal user records.
- **Performance** — Response caching and connection pooling for AgentCore API calls to minimize latency.

All AgentCore services are accessed through a unified integration facade (`agentcore_integration.py`) that handles initialization, error handling, and graceful degradation when AgentCore is not configured.

### Permission System

Granular data access permissions that members grant or revoke at their own discretion. Each agent declares which permissions it requires, and the system checks these before allowing agent execution.

**Permission types:**
- `email_access` -- Allow agents to read and draft emails
- `calendar_access` -- Allow agents to access calendar data
- `health_data` -- Allow agents to read health observations and records
- `medical_records` -- Allow agents to access medical documents

Members can view required permissions per agent and grant/revoke them individually via the permissions API.

### Family Management

Families are created during the first admin registration. Additional members join via invite codes (generated by admin) or email invitations. The family tree tracks relationships between members (parent, child, spouse, sibling) and injects family context into the system prompt so Claude understands who it is talking to and the family structure.

### Health Management

A comprehensive health tracking system with multiple data layers:

- **Health Records** -- Structured health data entries (conditions, medications, allergies, vitals)
- **Health Observations** -- Timestamped observations and notes
- **Health Documents** -- File uploads (PDFs, images) stored in S3 with metadata in DynamoDB
- **Health Reports** -- AI-generated health summaries and recommendations
- **Automated Health Extraction** -- When enabled, the system analyzes chat conversations using a separate Claude model (Haiku) to automatically extract health-relevant information and create observations
- **Audit Trail** -- Every health data change is logged for accountability

### Admin Panel

The mobile app includes an admin dashboard for family administrators:

- Member management (view all members, edit profiles, remove members)
- Agent authorization per member (control which agents each member can access)
- Agent template management (create, edit, delete custom agent types)
- Invite code generation for onboarding new family members

### Member Profiles

Each member has a customizable profile including display name, family role, health notes, interests, and preferences. Profile data is injected into the system prompt to personalize Claude's responses.

### Authentication

Dual authentication strategy:

1. **AWS Cognito** -- Email/password authentication with JWT tokens. The backend verifies Cognito JWTs and maps the `sub` claim to the internal user record.
2. **Device Token Fallback** -- A 64-character base64url token generated at registration, stored in `expo-secure-store` on the device. Used when Cognito is not configured or as a simpler alternative.

Both methods are tried in sequence on each request. The `Authorization: Bearer <token>` header carries either a Cognito JWT or a device token.

### Debug Web Console

A browser-based admin and testing tool located in `webui/`. Built as static HTML/CSS/JS (no build step), it connects to the backend API and provides a full-featured interface for testing chat, managing members, and monitoring the system. Hosted on S3 with CloudFront distribution in production.

---

## How It Works

### App Flow Overview

A family admin registers and creates the family workspace. They invite family members via codes or email. The admin authorizes which AI agents each member can use. Members then chat with Claude through the app — Claude is personalized with their profile, family context, and health history. Specialized agents (health advisor, logistics assistant) can be invoked automatically during conversations based on the topic. Members control their own data permissions, deciding what the AI can access.

### Key User Flows (Brief)

1. **Onboarding**

```
Admin registers → Creates family → Invites members → Authorizes agents
```

2. **Chat**

```
User types message → Backend streams to Claude → Response appears token-by-token → Health data auto-extracted
```

3. **Voice**

```
User speaks → Audio streamed via WebSocket → Nova Sonic responds in real-time
```

4. **Agent Authorization**

```
Admin enables agent for member → Member enables it for themselves → Member grants required permissions → Agent becomes available in chat
```

5. **Health Tracking**

```
Health records created manually + auto-extracted from chats → Health Advisor agent uses records during conversations → Admin generates AI health reports
```

### Design Philosophy

- **Family-centric**: Shared workspace with per-member personalization and admin oversight
- **Privacy by design**: 2-layer permission model — admin controls access, members control their data
- **Agent extensibility**: New agents can be added at runtime without code changes
- **Mobile-first**: Phone is the primary interface; web console for admin/debug

For detailed architecture, user scenarios, and end-to-end flow diagrams, see [Architecture & Design](docs/architecture-and-design.md).

---

## Architecture

```
                                    +--------------------+
                                    |   Expo Mobile App  |
                                    |  (React Native TS) |
                                    +--------+-----------+
                                             |
                              HTTP / SSE / WebSocket
                                             |
                    (dev: cloudflared tunnel / prod: ALB)
                                             |
+------------------+           +-------------v------------+           +------------------+
|   S3 Bucket      |<--------->|   Flask API (ECS Fargate)|<--------->|   DynamoDB       |
| - chat media     | presigned |   - /api/chat     (SSE)  |  14 tables| - Users          |
| - health docs    | URLs      |   - /api/voice    (WS)   |           | - Conversations  |
| - audio uploads  |           |   - /api/health/*        |           | - Messages       |
| - transcripts    |           |   - /api/agents/*        |           | - ChatMedia      |
+------------------+           +--+---+-----+--------+----+           | - HealthRecords  |
                                  |   |     |        |                | - AgentTemplates |
                            +-----v-+ | +---v---+ +--v-----------+   | - Profiles ...   |
                            | Bedrock| | | Trans-| | Strands      |  +------------------+
                            | Claude | | | cribe | | Agent SDK    |
                            +--------+ | +-------+ +--------------+
                                       |                 |
                    +------------------v---------+  +----v---------+
                    | Amazon Bedrock AgentCore   |  | Nova Sonic   |
                    | - Runtime (orchestration)  |  | (Voice Mode) |
                    | - Memory  (family+member)  |  +--------------+
                    | - Gateway (MCP tools)      |
                    | - Identity (Cognito auth)  |
+------------------+| - Cognito User Pool        |
| CloudFront + S3  |+---------------------------+
| (Debug Web UI)   |
+------------------+
```

**Request flow (text chat):** Mobile app sends a POST to `/api/chat/stream` with the message and optional image references. The backend loads conversation history from DynamoDB, resolves any image media from S3, calls Bedrock `converse_stream`, and pipes the response back as SSE events. The assistant message is persisted to DynamoDB upon completion.

**Request flow (voice mode):** Mobile app opens a WebSocket to `/api/voice?token=<token>`. The backend establishes a bidirectional stream with Amazon Nova Sonic. Audio frames flow in both directions in real time.

**Monorepo layout:** `backend/` (Flask API), `mobile/` (Expo React Native), `webui/` (static debug console), `infra/` (AWS CDK stacks).

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Mobile | Expo React Native (TypeScript), SDK 54, expo-av, expo-file-system, expo-secure-store, expo-updates |
| Backend | Python 3.12, Flask, Gunicorn + gevent, boto3 |
| AI Models | Amazon Bedrock (Claude), AWS Transcribe, Amazon Nova Sonic |
| Agents | Strands Agents SDK + Amazon Bedrock AgentCore |
| AgentCore | Runtime (orchestration), Memory (persistent), Gateway (MCP tools), Identity (Cognito) |
| Database | Amazon DynamoDB (14 tables, on-demand billing) |
| Storage | Amazon S3 (chat media, health documents, audio, transcripts) |
| Auth | Amazon Cognito (email/password JWT) + device token fallback |
| Compute | Amazon ECS Fargate |
| Networking | Application Load Balancer (300s idle timeout for SSE/WebSocket) |
| CDN | Amazon CloudFront (debug web console hosting) |
| IaC | AWS CDK (Python), one stack per concern |
| CI/CD | AWS CodePipeline + CodeBuild + CDK Pipelines (5 pipelines) |

---

## Project Structure

```
homeagent/
  backend/
    app/
      __init__.py              # Flask app factory
      auth.py                  # Cognito JWT + device token auth
      config.py                # Environment-based configuration
      models/
        dynamo.py              # DynamoDB table helpers and auto-init
      routes/
        chat.py                # SSE streaming chat endpoint
        chat_media.py          # Presigned URL upload management
        voice.py               # WebSocket voice mode
        conversations.py       # Conversation CRUD
        profiles.py            # Member profiles
        family_tree.py         # Relationship management
        health.py              # Health check endpoint
        health_records.py      # Health records CRUD
        health_documents.py    # Document upload/download
        health_reports.py      # AI-generated health reports
        auth_routes.py         # Registration, login, admin, family
        agent_config_routes.py # Per-user agent settings
        agent_template_routes.py # Admin agent templates
        agentcore_agent_routes.py # AgentCore agent management
        member_agent_routes.py # User-facing agent listing
        permission_routes.py   # Member permission management
        session_routes.py      # Session bootstrap (single-call init)
        memory_routes.py       # Memory management endpoints
        storage_routes.py      # Storage provider configuration
        storage_migration_routes.py # Storage migration endpoints
      services/
        bedrock.py             # Claude converse_stream integration
        transcribe.py          # AWS Transcribe (voice-to-chat)
        chat_media.py          # S3 presigned URL + media resolution
        conversation.py        # Conversation/message persistence
        voice_session.py       # Nova Sonic WebSocket session
        agent_orchestrator.py  # Strands agent routing
        agent_config.py        # Agent configuration service
        agent_template.py      # Agent template CRUD + built-in seeding
        agent_management.py    # Agent lifecycle management
        agentcore_runtime.py   # AgentCore Runtime orchestration
        agentcore_memory.py    # AgentCore Memory (family + member)
        agentcore_gateway.py   # AgentCore MCP tool gateway
        agentcore_security.py  # AgentCore Identity + Cognito auth
        agentcore_performance.py # AgentCore caching + optimization
        agentcore_integration.py # Unified AgentCore facade
        family_memory.py       # Family-scoped shared memory
        health_extraction.py   # AI health data extraction from chats
        health_records.py      # Health records service
        health_observations.py # Health observations service
        health_documents.py    # S3 document management
        health_audit.py        # Audit trail
        member_permissions.py  # Permission grant/revoke/check
        profile.py             # Profile service
        family_tree.py         # Family relationship service
        family.py              # Family management
        cognito.py             # Cognito JWT verification
        memory.py              # AgentCore memory integration
        storage_config.py      # Storage provider configuration
        storage_migration.py   # Storage migration service
        user.py                # User/device management
      agents/
        registry.py            # Agent registration decorator + factory
        personal.py            # Personal assistant (main orchestrator)
        health_advisor.py      # Health advisor sub-agent
        health_tools.py        # Health-related agent tools
        custom_agent.py        # Dynamic agent from templates
    tests/                     # pytest test suite
    Dockerfile
    requirements.txt
  mobile/
    src/
      screens/
        ChatScreen.tsx              # Main chat with SSE streaming
        VoiceModeScreen.tsx         # Full-screen voice mode
        RegisterScreen.tsx          # Device registration
        SettingsScreen.tsx          # App settings
        ProfileScreen.tsx           # User profile editor
        FamilyTreeScreen.tsx        # Family relationships
        ConversationListScreen.tsx  # Conversation history
        MyAgentsScreen.tsx          # User agent configuration
        AdminPanelScreen.tsx        # Admin dashboard
        AdminMembersScreen.tsx      # Member management
        AdminMemberDetailScreen.tsx # Member detail/edit
        AdminAgentTemplatesScreen.tsx # Agent template management
      components/
        ChatInput.tsx               # Text input + image picker + mic
        MessageBubble.tsx           # Chat message display
        VoiceButton.tsx             # Mic button with recording state
        ImageAttachment.tsx         # Image preview thumbnail
      services/
        api.ts                      # HTTP client with auth headers
        sse.ts                      # SSE streaming client
        chatMedia.ts                # Image/audio upload via presigned URLs
        voiceSession.ts             # WebSocket voice session client
        auth.ts                     # Secure token storage
    app.json
    package.json
  webui/
    index.html                      # Debug web console (static)
  infra/
    stacks/
      network_stack.py              # VPC, subnets, security groups
      data_stack.py                 # DynamoDB tables (14), S3 bucket
      agentcore_stack.py            # Cognito User Pool, AgentCore tables, SSM params
      security_stack.py             # IAM roles, ECR, Bedrock/Transcribe/AgentCore perms
      service_stack.py              # ECS Fargate, ALB, auto-scaling, AgentCore env vars
      webui_stack.py                # S3 + CloudFront for debug console
      pipeline_stack.py             # CI/CD pipelines (main + 4 fast pipelines)
    app.py
    requirements.txt
  docs/                             # Detailed documentation
  docker-compose.yml                # Local dev (Flask + DynamoDB Local + MinIO)
  .env.example                      # Environment variable template
  CLAUDE.md                         # Project conventions for AI assistants
```

---

## Getting Started

### Prerequisites

- **Docker** and **Docker Compose** -- for running the backend locally
- **Node.js 18+** -- for the mobile app
- **Expo Go** app installed on your phone (iOS or Android)
- **AWS credentials** -- with Bedrock Claude access (for AI features)
- Python 3.12+ (optional, for running infra CDK commands)

### Local Development

**1. Configure environment variables**

```bash
cp .env.example .env
# Edit .env with your Cognito pool details (optional for local dev)
```

**2. Start the backend**

```bash
docker compose up
```

This launches three services:
- **Flask API** on `http://localhost:5000` (with hot reload via volume mount)
- **DynamoDB Local** on `http://localhost:8000`
- **MinIO** (S3-compatible) on `http://localhost:9000` (console on `http://localhost:9001`)

DynamoDB tables are auto-created on first request. MinIO bucket is initialized automatically.

**3. Start the mobile app**

```bash
cd mobile
npm install
npx expo start
```

Scan the QR code with Expo Go on your phone. The app will connect to the backend.

**4. Connect your phone to the local backend**

If your phone and dev machine are on the same network, Expo Go can reach `http://<your-local-ip>:5000`. For remote testing or when networks differ, use a cloudflared tunnel:

```bash
cloudflared tunnel --url http://localhost:5000
```

Update the API base URL in the mobile app settings to the tunnel URL.

**5. Debug web console**

```bash
python -m http.server 8080 -d webui
```

Open `http://localhost:8080` in a browser and set the API endpoint to `http://localhost:5000`.

---

## Deployment

HomeAgent uses AWS CDK Pipelines for automated CI/CD. Five pipelines handle different parts of the system.

### First-Time Setup

```bash
# 1. Create a CodeStar Connection to GitHub in the AWS Console
#    (Developer Tools > Settings > Connections > Create connection)

# 2. Bootstrap CDK
cd infra
pip install -r requirements.txt
cdk bootstrap aws://ACCOUNT_ID/us-east-1

# 3. Deploy the pipeline stack
cdk deploy HomeAgentPipeline \
  -c account=ACCOUNT_ID \
  -c region=us-east-1 \
  -c github_connection_arn=arn:aws:codeconnections:us-east-1:ACCOUNT_ID:connection/UUID

# 4. Push to main to trigger the pipeline
git push origin main
```

### CI/CD Pipelines

| Pipeline | Trigger | Flow |
|----------|---------|------|
| `homeagent-pipeline` | Manual / infra pipeline | CDK Synth -> Test -> Deploy all stacks -> Docker build -> ECS deploy -> WebUI sync |
| `homeagent-backend-fast` | Push to `main` (backend/**) | Test (pytest) -> Docker build -> ECS deploy (~5 min) |
| `homeagent-webui-fast` | Push to `main` (webui/**) | S3 sync -> CloudFront invalidation (~1 min) |
| `homeagent-infra` | Push to `main` (infra/**) | CDK synth -> CDK deploy (~5 min) |
| `homeagent-mobile` | Push to `main` (mobile/**) | TypeScript check -> Expo publish -> Test URL (~3 min) |

### Infrastructure Stacks

| Stack | Resources |
|-------|-----------|
| `NetworkStack` | VPC, subnets, security groups |
| `DataStack` | 14 DynamoDB tables, S3 bucket |
| `AgentCoreStack` | Cognito User Pool + Client, AgentCore DynamoDB tables, SSM parameters |
| `SecurityStack` | IAM roles, ECR repository, Bedrock/Transcribe/AgentCore permissions |
| `ServiceStack` | ECS Fargate service, ALB (300s idle timeout), auto-scaling, AgentCore env vars |
| `WebUiStack` | S3 bucket + CloudFront distribution for debug console |
| `PipelineStack` | All 5 CodePipeline definitions |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region for all services |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-opus-4-6-v1` | Claude model ID for chat |
| `SYSTEM_PROMPT` | (friendly assistant) | System prompt injected into every conversation |
| `ADMIN_INVITE_CODE` | -- | Pre-seeded invite code for bootstrapping the first admin |
| `S3_HEALTH_DOCUMENTS_BUCKET` | -- | S3 bucket name for all file storage (images, audio, docs) |
| `CHAT_MEDIA_MAX_SIZE` | `5242880` (5 MB) | Maximum image upload size in bytes |
| `CHAT_MEDIA_AUDIO_MAX_SIZE` | `26214400` (25 MB) | Maximum audio upload size in bytes |
| `USE_AGENT_ORCHESTRATOR` | `false` | Enable Strands Agent orchestrator for sub-agent routing |
| `HEALTH_EXTRACTION_ENABLED` | `true` | Enable AI-powered health data extraction from chats |
| `HEALTH_EXTRACTION_MODEL_ID` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Model used for health extraction |
| `VOICE_ENABLED` | `false` | Enable voice mode WebSocket endpoint |
| `VOICE_MODEL_ID` | `amazon.nova-sonic-v1:0` | Nova Sonic model ID for voice mode |
| `COGNITO_USER_POOL_ID` | -- | Cognito User Pool ID (from AgentCore stack) |
| `COGNITO_CLIENT_ID` | -- | Cognito App Client ID (from AgentCore stack) |
| `COGNITO_REGION` | `us-east-1` | Region for Cognito User Pool |
| `AGENTCORE_ORCHESTRATOR_AGENT_ID` | -- | AgentCore Runtime orchestrator agent ID |
| `AGENTCORE_RUNTIME_ENDPOINT` | -- | AgentCore Runtime endpoint URL |
| `AGENTCORE_FAMILY_MEMORY_ID` | -- | AgentCore Memory store ID for family memories |
| `AGENTCORE_MEMBER_MEMORY_ID` | -- | AgentCore Memory store ID for member memories |
| `AGENTCORE_GATEWAY_ID` | -- | AgentCore Gateway ID for MCP tool routing |
| `HEALTH_MCP_ENDPOINT` | -- | MCP server endpoint for health tools |
| `FAMILY_MCP_ENDPOINT` | -- | MCP server endpoint for family tree tools |
| `SES_ENABLED` | `false` | Enable SES for email invitations |
| `SES_FROM_EMAIL` | -- | Sender email address for SES |
| `DYNAMODB_ENDPOINT` | -- | DynamoDB endpoint override (local dev: `http://dynamodb-local:8000`) |
| `S3_ENDPOINT` | -- | S3 endpoint override (local dev: `http://minio:9000`) |
| `TABLE_PREFIX` | -- | Optional prefix for all DynamoDB table names |

---

## API Overview

All endpoints are prefixed with `/api/` except the health check. Authentication is required on most endpoints via `Authorization: Bearer <token>`.

| Group | Endpoints | Description |
|-------|-----------|-------------|
| **Health Check** | `GET /health` | Service health (no auth) |
| **Auth** | `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/cognito/register` | Registration and authentication |
| **Session** | `GET /api/session` | Bootstrap all user data in a single call |
| **Chat** | `POST /api/chat/stream`, `POST /api/chat/upload-image`, `POST /api/chat/upload-audio` | Streaming chat and media uploads |
| **Voice** | `WS /api/voice` | Real-time voice mode via WebSocket |
| **Conversations** | `GET/DELETE /api/conversations/*` | Conversation list, history, deletion |
| **Profiles** | `GET/PUT /api/profiles/me` | Member profile management |
| **Family** | `GET/POST /api/family/*`, `GET/POST/DELETE /api/family-tree/*` | Family management and relationship tree |
| **Health** | `GET/POST /api/health-records/*`, `GET/POST /api/health-observations/*`, `GET/POST /api/health-documents/*`, `GET /api/health-reports/*` | Health data management |
| **Agents** | `GET/PUT /api/agents/*`, `GET /api/member-agents/*`, `GET/POST /api/agentcore/*` | Agent configuration, listing, and AgentCore management |
| **Memory** | `GET/POST /api/memory/*` | Memory store management |
| **Permissions** | `GET/PUT/DELETE /api/permissions/*` | Data permission management |
| **Storage** | `GET/POST /api/storage/*`, `POST /api/storage/migrate` | Storage provider config and migration |
| **Admin** | `GET/POST/PUT/DELETE /api/admin/*` | Member management, agent templates, health records (admin only) |

For complete endpoint documentation with request/response formats, see [docs/API.md](docs/API.md).

---

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System design, deployment topology, data model, DynamoDB table schemas |
| [API Reference](docs/API.md) | All endpoints with request/response formats and examples |
| [Deployment Guide](docs/DEPLOYMENT.md) | AWS setup, pipeline configuration, scaling, monitoring, rollback |
| [Developer Guide](docs/DEVELOPMENT.md) | Local setup, testing, code conventions, adding new features |
| [User Manual](docs/USER_MANUAL.md) | End-user guide for installing, registering, and using the app |
| [Test Guide](TEST_GUIDE.md) | Manual test cases for all features (17 scenarios) |

---

## Data Model

14 DynamoDB tables with on-demand billing:

| Table | Key | Purpose |
|-------|-----|---------|
| Users | `user_id` | User accounts and metadata |
| Devices | `user_id` + `device_id` | Device tokens for auth |
| Conversations | `user_id` + `sort_key` | Chat conversations |
| Messages | `conversation_id` + `sort_key` | Chat messages |
| ChatMedia | `media_id` | Image/audio upload tracking |
| Profiles | `user_id` | Member profiles and preferences |
| FamilyRelationships | `user_id` + `related_user_id` | Family tree edges |
| HealthRecords | `user_id` + `sort_key` | Structured health data |
| HealthObservations | `user_id` + `sort_key` | Timestamped health notes |
| HealthDocuments | `user_id` + `sort_key` | Document metadata (files in S3) |
| HealthAudit | `user_id` + `sort_key` | Audit trail for health changes |
| AgentConfigs | `user_id` + `agent_type` | Per-user agent settings |
| AgentTemplates | `template_id` | Agent type definitions |
| InviteCodes | `code` | Registration invite codes |
| MemberPermissions | `user_id` + `permission_type` | Granted data permissions |
