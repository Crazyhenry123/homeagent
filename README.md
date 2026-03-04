# HomeAgent

A family AI assistant app where family members chat with Claude (via Amazon Bedrock) through a mobile app. Supports text chat with SSE streaming, image attachments, voice-to-chat with automatic transcription, real-time voice mode, an extensible agent system, and family health management.

## Features

### Text Chat
- Real-time streaming responses via Server-Sent Events (SSE)
- Claude via Amazon Bedrock `converse_stream` API
- Conversation history with auto-titling
- Configurable system prompt and model selection

### Image Attachments
- Up to 5 images per message
- S3 presigned PUT URL upload pipeline (client uploads directly to S3)
- Supports JPEG, PNG, GIF, WebP
- Images passed as multimodal content blocks to Claude

### Voice-to-Chat
- Inline mic recording in chat input (tap to record, tap to stop)
- Audio uploaded to S3 as WAV via the same presigned URL pipeline
- Server-side transcription via AWS Transcribe
- Auto language detection (en-US, zh-CN)
- Transcribed text sent to Claude as a regular message
- 25MB max audio upload size

### Voice Mode
- Bidirectional WebSocket audio streaming
- Amazon Nova Sonic for real-time speech-to-speech
- Separate full-screen voice interface

### Agent System
- Pluggable sub-agent architecture via Strands SDK
- Built-in agents: Health Advisor, Personal Assistant
- Custom agent support with configurable templates
- Per-user agent enable/disable and configuration
- Admin-managed agent templates

### Health Management
- Health records and observations tracking
- Document uploads (PDFs, images) with S3 storage
- AI-powered health extraction from chat conversations
- Health reports generation
- Full audit trail for all health data changes

### Family Management
- Family tree with relationship tracking (parent, child, spouse, sibling)
- Per-member profiles (name, role, interests, health notes)
- Family context injection into system prompt
- Admin and member role separation

## Architecture

```
                                    +-------------------+
                                    |   Expo Mobile App |
                                    |   (React Native)  |
                                    +--------+----------+
                                             |
                              HTTP/SSE/WebSocket
                                             |
+------------------+            +------------v-----------+           +----------------+
|   S3 Bucket      |<---------->|   Flask API (ECS)      |<--------->| DynamoDB       |
| - chat media     |  presigned |   - /api/chat (SSE)    |  14 tables| - Users        |
| - health docs    |  URLs      |   - /api/voice (WS)    |           | - Conversations|
| - audio uploads  |            |   - /api/health/*      |           | - Messages     |
| - transcripts    |            |   - /api/profiles/*    |           | - ChatMedia    |
+------------------+            +---+----------+----+----+           | - HealthRecords|
                                    |          |    |                | - Agents...    |
                              +-----v---+ +----v--+ +---v--------+  +----------------+
                              | Bedrock  | | Trans | | Strands    |
                              | Claude   | | cribe | | Agent SDK  |
                              +---------+  +------+  +------------+
```

### Backend (`backend/`)

Flask API application (Python 3.12) deployed on ECS Fargate behind an ALB.

```
backend/app/
  __init__.py          # Flask app factory
  config.py            # Environment-based configuration
  auth.py              # Bearer token authentication
  models/
    dynamo.py          # DynamoDB table helpers and auto-init
  routes/
    chat.py            # SSE streaming chat endpoint
    chat_media.py      # Presigned URL upload management
    voice.py           # WebSocket voice mode
    conversations.py   # Conversation CRUD
    profiles.py        # Member profiles
    family_tree.py     # Relationship management
    health.py          # Health observations
    health_records.py  # Health records CRUD
    health_documents.py # Document upload/download
    health_reports.py  # AI-generated health reports
    auth_routes.py     # Registration and device management
    agent_config_routes.py    # Per-user agent settings
    agent_template_routes.py  # Admin agent templates
    member_agent_routes.py    # User-facing agent listing
  services/
    bedrock.py         # Claude converse_stream integration
    transcribe.py      # AWS Transcribe (voice-to-chat)
    chat_media.py      # S3 presigned URL + media resolution
    conversation.py    # Conversation/message persistence
    voice_session.py   # Nova Sonic WebSocket session
    agent_orchestrator.py  # Strands agent routing
    health_extraction.py   # AI health data extraction
    health_records.py  # Health records service
    health_observations.py # Health observations service
    health_documents.py # S3 document management
    health_audit.py    # Audit trail
    profile.py         # Profile service
    family_tree.py     # Family relationship service
    memory.py          # AgentCore memory integration
    user.py            # User/device management
    agent_config.py    # Agent configuration service
    agent_template.py  # Agent template service
  agents/
    registry.py        # Agent registration decorator
    personal.py        # Personal assistant agent
    health_advisor.py  # Health advisor agent
    health_tools.py    # Health-related agent tools
    custom_agent.py    # Custom agent from templates
```

### Mobile (`mobile/`)

Expo React Native app (TypeScript, SDK 52) with managed workflow.

```
mobile/src/
  screens/
    ChatScreen.tsx           # Main chat with SSE streaming
    VoiceModeScreen.tsx      # Full-screen voice mode
    RegisterScreen.tsx       # Device registration
    SettingsScreen.tsx       # App settings
    ProfileScreen.tsx        # User profile editor
    FamilyTreeScreen.tsx     # Family relationships
    ConversationListScreen.tsx # Conversation history
    MyAgentsScreen.tsx       # User agent configuration
    AdminPanelScreen.tsx     # Admin dashboard
    AdminMembersScreen.tsx   # Member management
    AdminMemberDetailScreen.tsx # Member detail/edit
    AdminAgentTemplatesScreen.tsx # Agent template management
  components/
    ChatInput.tsx            # Text input + image picker + voice recording
    MessageBubble.tsx        # Chat message display
    VoiceButton.tsx          # Mic button with recording state
    ImageAttachment.tsx      # Image preview thumbnail
    ConversationItem.tsx     # Conversation list item
  services/
    api.ts                   # HTTP client with auth headers
    sse.ts                   # SSE streaming client
    chatMedia.ts             # Image/audio upload via presigned URLs
    voiceSession.ts          # WebSocket voice session client
    auth.ts                  # Secure token storage
    authEvents.ts            # Auth state event emitter
```

### Web Debug Console (`webui/`)

Static HTML/CSS/JS debug console hosted on S3 + CloudFront. Full-featured admin interface for testing and monitoring.

### Infrastructure (`infra/`)

AWS CDK Python stacks deployed via CDK Pipelines.

| Stack | Purpose |
|-------|---------|
| `NetworkStack` | VPC, subnets, security groups |
| `DataStack` | DynamoDB tables (14), S3 bucket |
| `SecurityStack` | IAM roles, ECR repo, Bedrock/Transcribe permissions |
| `ServiceStack` | ECS Fargate service, ALB, auto-scaling |
| `WebUiStack` | S3 bucket + CloudFront for debug console |
| `PipelineStack` | CI/CD pipelines (main + fast pipelines) |

## Data Model

14 DynamoDB tables (on-demand billing):

| Table | Key | Purpose |
|-------|-----|---------|
| Users | `user_id` | User accounts and device tokens |
| Conversations | `user_id` + `sort_key` | Chat conversations |
| Messages | `conversation_id` + `sort_key` | Chat messages |
| ChatMedia | `media_id` | Image/audio upload tracking |
| Profiles | `user_id` | Member profiles and preferences |
| FamilyRelationships | `user_id` + `related_user_id` | Family tree |
| HealthRecords | `user_id` + `sort_key` | Health records |
| HealthObservations | `user_id` + `sort_key` | Health observations |
| HealthDocuments | `user_id` + `sort_key` | Health document metadata |
| HealthAudit | `user_id` + `sort_key` | Audit trail |
| AgentConfigs | `user_id` + `agent_type` | Per-user agent settings |
| AgentTemplates | `template_id` | Agent template definitions |
| InviteCodes | `code` | Registration invite codes |
| DeviceTokens | `device_token` | Device authentication |

## CI/CD

Five pipelines in AWS CodePipeline:

| Pipeline | Trigger | Flow |
|----------|---------|------|
| `homeagent-pipeline` | Manual / infra pipeline | Synth CDK -> Test -> Deploy all stacks -> Docker build -> ECS deploy -> WebUI sync |
| `homeagent-backend-fast` | Push to `main` (backend/**) | Test (pytest) -> Docker build -> ECS deploy (~5 min) |
| `homeagent-webui-fast` | Push to `main` (webui/**) | S3 sync -> CloudFront invalidation (~1 min) |
| `homeagent-infra` | Push to `main` (infra/**) | CDK deploy -> triggers main pipeline for app stacks |
| `homeagent-mobile` | Push to `main` (mobile/**) | TypeScript type check validation |

## Getting Started

### Prerequisites
- AWS account with Bedrock Claude access
- Node.js 18+, Python 3.12+, Docker
- Expo Go app on your phone

### Local Development

```bash
# Backend (Flask + DynamoDB Local + MinIO for S3)
docker compose up

# Mobile
cd mobile
npm install
npx expo start    # Scan QR code with Expo Go

# Web Debug Console
python -m http.server 8080 -d webui
# Configure API endpoint to http://localhost:5000
```

### Cloud Deployment

```bash
# 1. Create a CodeStar Connection to GitHub in AWS Console
# 2. Bootstrap CDK
cd infra
pip install -r requirements.txt
cdk bootstrap aws://ACCOUNT_ID/us-east-1

# 3. Deploy pipeline
cdk deploy HomeAgentPipeline \
  -c account=ACCOUNT_ID \
  -c region=us-east-1 \
  -c github_connection_arn=arn:aws:codeconnections:us-east-1:ACCOUNT_ID:connection/UUID

# 4. Push to main to trigger pipelines
git push origin main
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-opus-4-6-v1` | Claude model ID |
| `SYSTEM_PROMPT` | (friendly assistant) | System prompt for Claude |
| `ADMIN_INVITE_CODE` | - | Pre-seeded invite code for first admin |
| `S3_HEALTH_DOCUMENTS_BUCKET` | - | S3 bucket for all file storage |
| `CHAT_MEDIA_MAX_SIZE` | `5242880` (5MB) | Max image upload size |
| `CHAT_MEDIA_AUDIO_MAX_SIZE` | `26214400` (25MB) | Max audio upload size |
| `USE_AGENT_ORCHESTRATOR` | `false` | Enable Strands Agent orchestrator |
| `HEALTH_EXTRACTION_ENABLED` | `true` | AI health extraction from chats |
| `VOICE_ENABLED` | `false` | Enable voice mode WebSocket |
| `DYNAMODB_ENDPOINT` | - | DynamoDB endpoint (local dev only) |
| `S3_ENDPOINT` | - | S3 endpoint override (local dev only) |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Mobile | Expo React Native (TypeScript), expo-av, expo-file-system |
| Backend | Flask (Python 3.12), Gunicorn + gevent |
| AI | Amazon Bedrock (Claude), AWS Transcribe, Amazon Nova Sonic |
| Agents | Strands Agents SDK |
| Database | Amazon DynamoDB (14 tables, on-demand) |
| Storage | Amazon S3 |
| Compute | Amazon ECS Fargate |
| Networking | Application Load Balancer (300s idle timeout for SSE/WS) |
| CDN | Amazon CloudFront (debug web console) |
| CI/CD | AWS CodePipeline + CodeBuild + CDK Pipelines |
| IaC | AWS CDK (Python) |
