# HomeAgent — Architecture & Design

This document explains **how HomeAgent works end-to-end** — the big picture, the design philosophy, and detailed user scenarios showing how every feature flows through the system. Read this first before diving into the implementation-level docs (backend.md, mobile.md, infrastructure.md).

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Core Design Principles](#2-core-design-principles)
3. [User Journey: First-Time Setup](#3-user-journey-first-time-setup)
4. [User Scenario: Text Chat with Claude](#4-user-scenario-text-chat-with-claude)
5. [User Scenario: Image Attachment](#5-user-scenario-image-attachment)
6. [User Scenario: Voice-to-Chat](#6-user-scenario-voice-to-chat)
7. [User Scenario: Real-Time Voice Mode](#7-user-scenario-real-time-voice-mode)
8. [User Scenario: Health Management](#8-user-scenario-health-management)
9. [Agent System Deep Dive](#9-agent-system-deep-dive)
10. [Session Bootstrap & State Management](#10-session-bootstrap--state-management)
11. [Authentication Flow](#11-authentication-flow)
12. [Family & Permissions Model](#12-family--permissions-model)

---

## 1. System Architecture Overview

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER'S PHONE                                │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │              Expo React Native App (TypeScript)               │  │
│  │                                                               │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │  │
│  │  │  Chat    │ │  Voice   │ │  Agent   │ │  Admin Panel   │  │  │
│  │  │  Screen  │ │  Mode    │ │  Mgmt    │ │  (family,      │  │  │
│  │  │  (SSE)   │ │  (WS)    │ │  Screen  │ │   members,     │  │  │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ │   agents)      │  │  │
│  │       │             │            │        └───────┬────────┘  │  │
│  │  ┌────┴─────────────┴────────────┴────────────────┴────────┐  │  │
│  │  │              SessionContext (useReducer)                 │  │  │
│  │  │   user | profile | family | agents | permissions | convs│  │  │
│  │  └────────────────────────┬────────────────────────────────┘  │  │
│  │                           │ api.ts / sse.ts / voiceSession.ts │  │
│  └───────────────────────────┼───────────────────────────────────┘  │
└──────────────────────────────┼──────────────────────────────────────┘
                               │
                    HTTP / SSE / WebSocket
                               │
              ┌────────────────┴────────────────┐
              │  cloudflared tunnel (dev)        │
              │  Application Load Balancer (prod)│
              │  (300s idle timeout for SSE/WS)  │
              └────────────────┬────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────────────────┐
│                    Flask API  (ECS Fargate / Gunicorn + gevent)      │
│                                                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────────┐  │
│  │  Auth Layer  │  │  16 Route    │  │  Service Layer            │  │
│  │  Cognito JWT │  │  Blueprints  │  │  ┌─────────────────────┐ │  │
│  │  + device    │  │              │  │  │ Agent Orchestrator  │ │  │
│  │  token       │  │  /api/chat   │  │  │ (Strands SDK)       │ │  │
│  │              │  │  /api/voice  │  │  │  ┌───────────────┐  │ │  │
│  │  Sets g.user │  │  /api/session│  │  │  │ Health Advisor│  │ │  │
│  │  on every    │  │  /api/agents │  │  │  │ Logistics Ast│  │ │  │
│  │  request     │  │  /api/health │  │  │  │ Shopping Ast  │  │ │  │
│  │              │  │  /api/admin  │  │  │  │ Custom Agents │  │ │  │
│  └─────────────┘  │  /api/family │  │  │  └───────────────┘  │ │  │
│                    │  ...         │  │  └─────────────────────┘ │  │
│                    └──────────────┘  │  ┌─────────────────────┐ │  │
│                                      │  │ Health Extraction   │ │  │
│                                      │  │ (background thread) │ │  │
│                                      │  └─────────────────────┘ │  │
│                                      └───────────────────────────┘  │
└───────┬──────────┬──────────┬──────────┬──────────┬────────────────┘
        │          │          │          │          │
   ┌────┴───┐ ┌───┴────┐ ┌──┴───┐ ┌───┴────┐ ┌──┴──────────┐
   │DynamoDB│ │Bedrock │ │  S3  │ │Cognito │ │ Transcribe  │
   │17 tbls │ │Claude  │ │media │ │JWT auth│ │ en/zh voice │
   │        │ │        │ │docs  │ │        │ │ to text     │
   └────────┘ └────────┘ └──────┘ └────────┘ └─────────────┘
                  │
            ┌─────┴──────┐
            │ Nova Sonic  │
            │ (voice mode)│
            └─────────────┘
```

### Component Roles

| Component | Role |
|-----------|------|
| **Expo Mobile App** | The primary user interface. Handles registration, chat (with SSE streaming), voice recording, agent management, health data entry, and admin functions. All state is centralized in a React Context store bootstrapped from a single API call. |
| **Flask API** | The backend brain. Authenticates every request, orchestrates AI calls, manages data in DynamoDB, handles file uploads via S3 presigned URLs, and serves SSE streams and WebSocket connections. Runs on Gunicorn with gevent workers to support long-lived connections. |
| **DynamoDB** | Stores all application data across 17 tables — users, conversations, messages, health records, agent configs, permissions, family relationships, and more. On-demand billing, no capacity planning needed. |
| **Amazon Bedrock (Claude)** | The AI model that powers all chat conversations. Called via `converse_stream` for token-by-token streaming. Also used by the Health Extraction service (Haiku model) to analyze conversations for health data. |
| **Strands Agent SDK** | The agent orchestration framework. Routes conversations to specialized sub-agents (Health Advisor, Logistics, Shopping) based on context. Agents are registered as tools on a main orchestrator agent. |
| **S3** | Stores chat images, audio recordings, health documents, and transcription output. The app never uploads directly through the API — it uses presigned URLs for direct S3 access. |
| **Cognito** | Handles email/password authentication with JWT tokens. Optional — the system also supports device token auth as a simpler fallback. |
| **AWS Transcribe** | Converts voice recordings to text for the voice-to-chat feature. Supports auto-detection between English and Chinese. |
| **Nova Sonic** | Powers real-time voice mode — bidirectional speech-to-speech over WebSocket. Users speak naturally and hear AI responses in real time. |

### How a Message Travels Through the System

```
User taps Send
       │
       ▼
[Mobile: ChatScreen.tsx]
  POST /api/chat/stream with message text + optional media_ids
       │
       ▼
[API: auth.py → require_auth]
  Validates Bearer token (Cognito JWT or device token)
  Sets g.user_id, g.user_name, g.family_id
       │
       ▼
[API: routes/chat.py → stream_chat()]
  1. Loads conversation history (last N messages from DynamoDB)
  2. Resolves any image/audio media from S3
  3. Builds system prompt (base + profile + family context + agent configs)
  4. Saves user message to DynamoDB
       │
       ▼
[API: services/agent_orchestrator.py] ──or── [API: services/bedrock.py]
  If USE_AGENT_ORCHESTRATOR=true:                If false:
    Strands orchestrator decides whether            Direct Bedrock converse_stream
    to invoke sub-agents (health, logistics)        call with conversation history
    or respond directly
       │
       ▼
[SSE stream back to mobile]
  Events: {"type":"text","content":"..."} token by token
  Final:  {"type":"done","message_id":"..."}
       │
       ▼
[Mobile: sse.ts → ChatScreen]
  XHR-based SSE parser updates UI in real time
  Message bubble grows as tokens arrive
       │
       ▼
[API: background thread]
  If HEALTH_EXTRACTION_ENABLED:
    Haiku model analyzes conversation for health-relevant data
    Auto-creates HealthObservation records
```

### Deployment Topology

| | Local Development | Production |
|---|---|---|
| **API** | Docker container (Gunicorn + gevent) | ECS Fargate (1 vCPU, 2GB, auto-scales 1→4) |
| **Database** | DynamoDB Local (persistent volume) | DynamoDB (on-demand, AWS-managed) |
| **Storage** | MinIO (S3-compatible) | Amazon S3 |
| **Networking** | cloudflared tunnel to phone | ALB with 300s idle timeout |
| **Mobile** | Expo Go (dev server + tunnel) | Expo build (standalone app) |
| **Web Console** | `python -m http.server` | S3 + CloudFront |

---

## 2. Core Design Principles

### Family-First
Every feature is designed around a **family unit** — not individual users. When a family is created, all members share a workspace. The system prompt includes family context (who the user is, their family role, relationships). An admin oversees the family: managing members, authorizing agents, generating health reports. Claude knows it's talking to "Mom" or "Grandpa" and adjusts its tone and advice accordingly.

### Agent Extensibility
The agent system is designed to grow without changing core code. New capabilities are added as **agent templates** — an admin creates a template with a name, description, system prompt, and required permissions. The template becomes a new agent type that can be authorized for members. At runtime, the Strands orchestrator automatically routes conversations to the relevant agent based on context. Built-in agents (Health Advisor, Logistics, Shopping) ship with the platform; custom agents extend it.

### Privacy by Design
Data access is controlled through a **2-layer permission model**:
1. **Admin layer** — The family admin decides which agents each member can access. A child might only get the Shopping Assistant, while a parent gets the Health Advisor too.
2. **Member layer** — Each member decides what data they share. Even if the admin authorizes the Health Advisor, the member must explicitly grant `health_data` and `medical_records` permissions before the agent can access their records.

This means no one — not even the admin — can force data sharing on a member.

### Mobile-First
The phone is the primary interface. The entire UX is designed for quick, natural interactions: tap to chat, tap to record voice, pull to refresh. The web console exists for admin/debug purposes but is not the main product. All state management is optimized for mobile — a single bootstrap API call loads everything, and individual refresh actions keep the UI current without full reloads.

---

## 3. User Journey: First-Time Setup

This is the complete onboarding flow for a new family.

### Step 1: Admin Registers

```
User Action:  Download app → Open → Enter name, email, password, invite code "FAMILY"
```

**What happens:**
1. **Mobile** (`RegisterScreen.tsx`): User fills registration form, taps Register
2. **API** (`routes/auth_routes.py → register()`):
   - Validates invite code against `InviteCodes` table
   - Creates Cognito user (if Cognito configured)
   - Creates `Users` record with `role: admin`
   - Creates `Devices` record with a 64-char device token
   - Auto-creates a `Family` record (first admin creates the family)
   - Creates default `AgentConfigs` for built-in agents marked `is_default: true`
   - Returns device token + user info
3. **Mobile** (`auth.ts`): Stores device token in `expo-secure-store`
4. **Mobile** (`AppNavigator.tsx`): Calls `bootstrap()` → `GET /api/session` → loads all data → navigates to Home

**Database writes:**
- `Users` — new admin user
- `Devices` — device token for auth
- `InviteCodes` — marks code as used
- `Families` — new family record
- `AgentConfigs` — default agent configs (health_advisor, logistics_assistant)

### Step 2: Admin Invites Family Members

```
User Action:  Settings → Open Admin Panel → Generate Invite Code
              (or: Family & Invites → Invite by Email)
```

**What happens:**
1. **Mobile** (`AdminPanelScreen.tsx`): Admin taps "Generate Invite Code"
2. **API** (`routes/auth_routes.py → generate_invite_code()`): Creates a random 8-char code in `InviteCodes` table, linked to the admin's family
3. **Mobile**: Shows alert with code to share (e.g., "ABC12345")

**Alternative — email invite:**
1. **Mobile** (`FamilyManageScreen.tsx`): Admin enters member's email
2. **API** (`routes/auth_routes.py → invite_by_email()`): Creates invite code + sends email via SES (if enabled)

### Step 3: Family Member Joins

```
User Action:  Download app → Register with invite code from admin
```

Same flow as Step 1, except:
- The invite code is linked to admin's family → member joins that family
- User gets `role: member` (not admin)
- Default agent configs are created for built-in agents

### Step 4: Admin Authorizes Agents per Member

```
User Action:  Admin Panel → Family Members → tap a member → toggle agents ON/OFF
```

**What happens:**
1. **Mobile** (`AdminMemberDetailScreen.tsx`): Shows all available agent types with toggles
2. **When admin toggles ON**: `PUT /api/admin/agent-configs/{userId}/{agentType}` → creates `AgentConfigs` record with `enabled: true`
3. **When admin toggles OFF**: `DELETE /api/admin/agent-configs/{userId}/{agentType}` → removes the `AgentConfigs` record entirely

**Key concept:** The existence of an `AgentConfigs` record = "admin has authorized this agent for this member." The `enabled` field = "member has chosen to turn it on."

### Step 5: Member Enables Their Agents

```
User Action:  Settings → My Agents → sees authorized agents → toggles ON
```

**What happens:**
1. **Mobile** (`MyAgentsScreen.tsx`):
   - Auto-refreshes on screen focus (`navigation.addListener('focus')`)
   - Filters available agents to only show ones with an `AgentConfigs` record (admin-authorized)
   - Shows each agent with description, permissions needed, and toggle
2. **When member toggles ON**: `PUT /api/agents/my/{agentType}` → sets `enabled: true` on existing config
3. **When member toggles OFF**: `DELETE /api/agents/my/{agentType}` → sets `enabled: false` (preserves admin authorization)

### Step 6: Member Grants Permissions

```
User Action:  My Agents → tap agent → expand permissions → toggle each permission ON
```

**What happens:**
1. **Mobile** (`MyAgentsScreen.tsx`): Expanded agent shows required permissions (e.g., "Health Data Access: Not granted")
2. **When member grants**: `PUT /api/permissions/{permissionType}` → creates `MemberPermissions` record
3. **When member revokes**: `DELETE /api/permissions/{permissionType}` → removes record

**Now the agent is fully operational** — admin authorized it, member enabled it, and required permissions are granted.

---

## 4. User Scenario: Text Chat with Claude

### What the User Sees
1. Taps "+" on the conversation list → new blank chat opens
2. Types "What should I make for dinner tonight? Dad is allergic to shellfish."
3. Hits send → message appears in chat bubble
4. Claude's response starts appearing immediately, word by word, in a growing bubble
5. Response completes in 3-5 seconds

### What Happens Under the Hood

```
Step  │ Where                              │ What
──────┼────────────────────────────────────┼─────────────────────────────────────
  1   │ Mobile: ConversationListScreen     │ POST /api/conversations → creates
      │                                    │ Conversations record, returns conv_id
──────┼────────────────────────────────────┼─────────────────────────────────────
  2   │ Mobile: ChatScreen.tsx             │ User types message, taps send
      │ services/sse.ts                    │ POST /api/chat/stream
      │                                    │   body: {conversation_id, content,
      │                                    │          media_ids: []}
      │                                    │   Accept: text/event-stream
──────┼────────────────────────────────────┼─────────────────────────────────────
  3   │ API: routes/chat.py                │ @require_auth validates token
      │ stream_chat()                      │ Loads last 50 messages from
      │                                    │ Messages table for context
──────┼────────────────────────────────────┼─────────────────────────────────────
  4   │ API: routes/chat.py                │ Builds system prompt:
      │                                    │   base_prompt (from env)
      │                                    │   + user profile (name, role, notes)
      │                                    │   + family context (members, tree)
      │                                    │   + agent instructions (if enabled)
──────┼────────────────────────────────────┼─────────────────────────────────────
  5   │ API: services/                     │ If USE_AGENT_ORCHESTRATOR=true:
      │ agent_orchestrator.py              │   Strands agent evaluates if
      │   └─ agents/personal.py            │   sub-agents should be invoked
      │       └─ agents/health_advisor.py  │   (health query? → Health Advisor)
      │                                    │ Else:
      │ services/bedrock.py                │   Direct Bedrock converse_stream
──────┼────────────────────────────────────┼─────────────────────────────────────
  6   │ API: routes/chat.py                │ Response streams as SSE events:
      │                                    │   data: {"type":"text","content":"I"}
      │                                    │   data: {"type":"text","content":"'d"}
      │                                    │   data: {"type":"text","content":" suggest"}
      │                                    │   ...
      │                                    │   data: {"type":"done","message_id":"..."}
──────┼────────────────────────────────────┼─────────────────────────────────────
  7   │ Mobile: sse.ts                     │ XHR-based SSE client parses events
      │ ChatScreen.tsx                     │ Updates streamingText state
      │                                    │ Message bubble re-renders each token
──────┼────────────────────────────────────┼─────────────────────────────────────
  8   │ API: routes/chat.py                │ On stream complete:
      │                                    │ Saves assistant message to Messages
      │                                    │ Updates conversation last_message_at
──────┼────────────────────────────────────┼─────────────────────────────────────
  9   │ API: services/                     │ If HEALTH_EXTRACTION_ENABLED:
      │ health_extraction.py               │ Background thread sends conversation
      │                                    │ to Haiku → extracts health data →
      │                                    │ creates HealthObservation records
```

### Why SSE (not WebSocket) for Chat?
- SSE is simpler — it's just HTTP with a long-lived response
- Unidirectional (server → client) is all that's needed for streaming responses
- Works through more proxies/firewalls than WebSocket
- The mobile SSE client uses XMLHttpRequest (not EventSource) because React Native doesn't support EventSource natively

---

## 5. User Scenario: Image Attachment

### What the User Sees
1. Taps the image picker icon in the chat input bar
2. Selects a photo from their gallery
3. Image thumbnail appears in the input area
4. Types "What's this rash on my arm?" and taps send
5. Claude responds with analysis of the image

### Technical Flow

```
Mobile                           API                              S3
  │                               │                                │
  │  POST /api/chat/upload-image  │                                │
  │  {content_type: "image/jpeg"} │                                │
  │──────────────────────────────>│                                │
  │                               │  Creates ChatMedia record      │
  │                               │  Generates presigned PUT URL   │
  │  {media_id, upload_url}       │                                │
  │<──────────────────────────────│                                │
  │                               │                                │
  │  PUT upload_url (binary)      │                                │
  │───────────────────────────────┼───────────────────────────────>│
  │                               │                                │  Stores image
  │  POST /api/chat/stream        │                                │
  │  {content, media_ids: ["..."]}│                                │
  │──────────────────────────────>│                                │
  │                               │  Resolves media_ids → S3 URLs  │
  │                               │  Downloads images from S3      │
  │                               │  Includes as image blocks in   │
  │                               │  Bedrock converse_stream call  │
  │                               │                                │
  │  SSE: streaming response      │                                │
  │<──────────────────────────────│                                │
```

**Key files:**
- `mobile/src/services/chatMedia.ts` — presigned upload logic
- `backend/app/routes/chat_media.py` — presigned URL generation
- `backend/app/services/chat_media.py` — media resolution for Bedrock
- `backend/app/routes/chat.py` — includes images in converse_stream call

**Why presigned URLs?** Images bypass the API entirely — the phone uploads directly to S3. This avoids loading the API with large binary payloads and keeps the API stateless.

---

## 6. User Scenario: Voice-to-Chat

### What the User Sees
1. In the chat input bar, taps the microphone button
2. Speaks: "What's a good pediatrician near downtown?"
3. Taps the mic button again to stop recording
4. A brief "Transcribing..." indicator appears
5. The transcribed text shows up as their chat message
6. Claude responds normally via streaming text

### Technical Flow

```
Mobile                           API                         AWS Services
  │                               │                                │
  │  [Records audio via expo-av]  │                                │
  │  [Saves as WAV file locally]  │                                │
  │                               │                                │
  │  POST /api/chat/upload-audio  │                                │
  │  {content_type: "audio/wav"}  │                                │
  │──────────────────────────────>│                                │
  │                               │  Creates ChatMedia record      │
  │  {media_id, upload_url}       │  (type: audio)                 │
  │<──────────────────────────────│                                │
  │                               │                                │
  │  PUT upload_url (WAV binary)  │                                │
  │───────────────────────────────┼──────────────────────────────>S3
  │                               │                                │
  │  POST /api/chat/stream        │                                │
  │  {content:"", media_ids:[…]}  │                                │
  │──────────────────────────────>│                                │
  │                               │  Detects audio media type      │
  │                               │  Calls AWS Transcribe ─────>Transcribe
  │                               │  (auto-detects en-US/zh-CN)    │
  │                               │  Gets transcribed text <────── │
  │                               │  Replaces audio with text      │
  │                               │  Calls Bedrock with text       │
  │                               │                                │
  │  SSE: streaming response      │                                │
  │<──────────────────────────────│                                │
```

**Key insight:** Voice-to-chat reuses the same chat pipeline — the audio is just transcribed into text before hitting Claude. The user's message in the conversation history shows the transcribed text, not the audio.

---

## 7. User Scenario: Real-Time Voice Mode

### What the User Sees
1. Navigates to Voice Mode screen (full-screen, dedicated UI)
2. Taps "Start" — microphone activates
3. Speaks naturally: "Tell me a bedtime story about a dragon"
4. Hears Claude's voice responding in real time (no text involved)
5. Can interrupt Claude mid-sentence by speaking (barge-in)
6. Taps "Stop" to end the session

### Technical Flow

```
Mobile (VoiceModeScreen)              API (voice.py)              Nova Sonic
  │                                     │                            │
  │  WS connect /api/voice?token=xxx    │                            │
  │────────────────────────────────────>│                            │
  │                                     │  Authenticate token        │
  │                                     │  Create Nova Sonic session │
  │                                     │────────────────────────────>│
  │                                     │  Send 6 setup events:      │
  │                                     │   - session config          │
  │                                     │   - audio input config      │
  │                                     │   - audio output config     │
  │                                     │   - system prompt           │
  │                                     │   - turn start              │
  │                                     │   - content start           │
  │                                     │────────────────────────────>│
  │                                     │                            │
  │  Audio frame (PCM bytes)            │                            │
  │────────────────────────────────────>│  Forward audio frame       │
  │                                     │────────────────────────────>│
  │  Audio frame                        │                            │
  │────────────────────────────────────>│────────────────────────────>│
  │  ...continuous audio stream...      │                            │
  │                                     │                            │
  │                                     │  Audio response frame      │
  │                                     │<────────────────────────────│
  │  Audio frame (WAV wrapped)          │                            │
  │<────────────────────────────────────│                            │
  │  [Plays through speaker]            │                            │
  │                                     │                            │
  │  WS close                           │                            │
  │────────────────────────────────────>│  Close Nova Sonic session  │
  │                                     │────────────────────────────>│
```

**Key details:**
- Audio flows as raw PCM frames in both directions
- The backend wraps outgoing audio in WAV headers so the mobile player can handle them
- gevent greenlets handle the bidirectional concurrency (one for send, one for receive)
- Nova Sonic supports barge-in — the user can interrupt Claude mid-response
- The system prompt includes the same family context as text chat

**Files:** `backend/app/routes/voice.py`, `backend/app/services/voice_session.py`, `mobile/src/screens/VoiceModeScreen.tsx`, `mobile/src/services/voiceSession.ts`

---

## 8. User Scenario: Health Management

### The Health Data Lifecycle

Health data enters the system through three paths and is used by the Health Advisor agent during conversations.

```
                    ┌──────────────────┐
                    │  Manual Entry    │  User or admin creates records
                    │  (health screens)│  via health API endpoints
                    └────────┬─────────┘
                             │
                             ▼
┌──────────────┐    ┌────────────────┐    ┌─────────────────┐
│ Document     │    │  DynamoDB      │    │ Auto-Extraction │
│ Upload       │───>│                │<───│ from Chat       │
│ (S3 + meta)  │    │ HealthRecords  │    │ (Haiku model)   │
└──────────────┘    │ HealthObs      │    └─────────────────┘
                    │ HealthDocs     │
                    │ HealthAudit    │
                    └───────┬────────┘
                            │
                            ▼
                    ┌────────────────┐
                    │ Health Advisor │  Queries records during chat
                    │ Agent          │  using health_tools.py
                    └────────────────┘
                            │
                            ▼
                    ┌────────────────┐
                    │ Health Reports │  AI-generated summaries
                    │ (on demand)    │  for admin review
                    └────────────────┘
```

### Path 1: Manual Entry
A user or admin creates health records through the API:
- **Health Records** — Structured data: conditions, medications, allergies, vitals, immunizations, procedures, lab results (7 record types)
- **Health Observations** — Timestamped notes: symptoms, diet, exercise, sleep, mood, general (6 categories)
- **Health Documents** — File uploads (PDFs, images) stored in S3 with metadata in DynamoDB

### Path 2: Auto-Extraction from Chat
When `HEALTH_EXTRACTION_ENABLED=true`:
1. After every chat response completes, a background thread fires
2. The full conversation is sent to Claude Haiku (cheaper, faster model)
3. Haiku analyzes the conversation for health-relevant information
4. Extracted data is automatically saved as `HealthObservation` records
5. This happens silently — the user doesn't see it

**Example:** User says "I've had a headache for 3 days and my blood pressure was 150/90 this morning." → Haiku extracts: symptom observation (headache, 3 days) + vitals observation (BP 150/90).

### Path 3: Health Advisor Agent in Chat
When the Health Advisor agent is enabled and the user asks a health question:
1. Strands orchestrator routes to Health Advisor sub-agent
2. Health Advisor has tools defined in `agents/health_tools.py`:
   - Query health records by type
   - Query recent observations
   - List health documents
   - Get family member health context
3. Agent retrieves relevant data, incorporates it into response
4. Provides personalized advice based on the member's actual health history

### Audit Trail
Every health data change (create, update, delete) is logged in the `HealthAudit` table with: who made the change, what changed, when, and the before/after state. This provides accountability for sensitive health data.

---

## 9. Agent System Deep Dive

### The Three Layers: Template → Config → Runtime

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1: Agent Templates (AgentTemplates table)                │
│  "What agents exist in the system"                              │
│                                                                  │
│  Created by: system (built-in) or admin (custom)                │
│  Contains: name, description, system_prompt, required_permissions│
│  Example: {agent_type: "health_advisor", name: "Health Advisor"} │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 2: Agent Configs (AgentConfigs table)                    │
│  "Which agents are authorized for which members"                │
│                                                                  │
│  Created by: admin (via AdminMemberDetailScreen)                │
│  Contains: user_id, agent_type, enabled (bool), custom config   │
│  Example: {user_id: "alice", agent_type: "health_advisor",      │
│            enabled: true}                                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 3: Runtime Execution                                     │
│  "Agent is invoked during a chat conversation"                  │
│                                                                  │
│  The orchestrator checks:                                        │
│  1. Does user have an AgentConfig for this agent? (admin auth)  │
│  2. Is it enabled? (member self-service)                         │
│  3. Are required permissions granted? (MemberPermissions table) │
│  If all yes → agent can be invoked                               │
└─────────────────────────────────────────────────────────────────┘
```

### Concrete Example: Alice and the Health Advisor

```
Timeline  │ Who    │ Action                                    │ Database Effect
──────────┼────────┼───────────────────────────────────────────┼──────────────────────
  Day 1   │ Admin  │ Opens AdminMemberDetail for Alice         │ (reads AgentConfigs)
          │ Admin  │ Toggles Health Advisor ON                 │ AgentConfigs: creates
          │        │                                           │   {alice, health_advisor,
          │        │                                           │    enabled: false}
──────────┼────────┼───────────────────────────────────────────┼──────────────────────
  Day 1   │ Alice  │ Opens My Agents screen                    │ (reads AgentConfigs)
          │ Alice  │ Sees Health Advisor (admin authorized)    │
          │ Alice  │ Toggles it ON                             │ AgentConfigs: updates
          │        │                                           │   enabled: true
──────────┼────────┼───────────────────────────────────────────┼──────────────────────
  Day 1   │ Alice  │ Taps Health Advisor → sees permissions    │
          │ Alice  │ Grants "Health Data Access"               │ MemberPermissions:
          │        │                                           │   {alice, health_data,
          │        │                                           │    status: active}
          │ Alice  │ Grants "Medical Records Access"           │ MemberPermissions:
          │        │                                           │   {alice, medical_records,
          │        │                                           │    status: active}
──────────┼────────┼───────────────────────────────────────────┼──────────────────────
  Day 2   │ Alice  │ Chats: "What are my current medications?" │
          │        │                                           │
          │ System │ Orchestrator sees health_advisor enabled  │
          │        │ + permissions granted → invokes agent     │
          │        │                                           │
          │ Agent  │ Health Advisor calls get_health_records   │ (reads HealthRecords)
          │        │ tool → finds medications list             │
          │        │                                           │
          │ Claude │ Responds with Alice's medication list     │
          │        │ and any relevant notes                    │
```

### How Chat Routes Through the Orchestrator

```python
# Simplified flow in agent_orchestrator.py

def handle_chat(user_id, message, conversation_history):
    # 1. Load user's enabled agents
    configs = get_agent_configs(user_id)  # AgentConfigs table
    enabled = [c for c in configs if c["enabled"]]

    # 2. Check permissions for each agent
    permissions = get_user_permissions(user_id)  # MemberPermissions table
    available_agents = []
    for config in enabled:
        template = get_template(config["agent_type"])
        required = template["required_permissions"]
        if all(p in permissions for p in required):
            available_agents.append(config["agent_type"])

    # 3. Register available agents as tools on the orchestrator
    orchestrator = create_orchestrator(available_agents)

    # 4. Orchestrator decides: answer directly or invoke a sub-agent
    response = orchestrator.run(message, conversation_history)

    # 5. Stream response back as SSE
    yield from response
```

### Built-in Agents and Their Tools

| Agent | Tools Available | What It Does |
|-------|----------------|--------------|
| **Health Advisor** | `get_health_records`, `get_observations`, `list_documents`, `get_family_health_context`, `create_observation`, `search_records`, `get_health_summary` | Queries the member's health data, creates observations, provides personalized health guidance with safety disclaimers |
| **Logistics Assistant** | (email drafting tools) | Helps draft emails and coordinate family schedules. Requires email_access and calendar_access permissions. |
| **Shopping Assistant** | (product search tools) | Product search and recommendations. No special permissions required. |
| **Custom Agents** | (none by default) | Admin-created agents with custom system prompts. Loaded dynamically from templates. |

---

## 10. Session Bootstrap & State Management

### The Single Bootstrap Call

When the app starts, it makes **one API call** that loads everything:

```
GET /api/session
Authorization: Bearer <token>

Response:
{
  "user": { "user_id", "name", "email", "role" },
  "profile": { "display_name", "family_role", "health_notes", "interests", ... },
  "family": {
    "info": { "family_id", "family_name", "created_at" },
    "members": [{ "user_id", "display_name", "role" }, ...]
  },
  "agents": {
    "available": [{ "agent_type", "name", "description", "enabled", "required_permissions", ... }],
    "my_configs": [{ "agent_type", "enabled", ... }],
    "agent_types": { "health_advisor": { "name", "description" }, ... }  // admin only
  },
  "permissions": [{ "permission_type", "status", "config" }, ...],
  "conversations": {
    "items": [{ "conversation_id", "title", "last_message_at" }, ...],
    "next_cursor": "..."
  }
}
```

**Why one call?** The previous design made 6+ API calls on startup, causing slow load times and race conditions. A single call eliminates waterfall requests and ensures consistent state.

### How State Flows Through the Mobile App

```
GET /api/session
       │
       ▼
useSession.bootstrap()
       │
       ▼
dispatch({ type: 'SESSION_BOOTSTRAP', payload: { ... } })
       │
       ▼
SessionContext (useReducer)
  ┌──────────────────────────────────────────────┐
  │ SessionState                                  │
  │   status: 'authenticated'                     │
  │   user: { userId, name, email, role }         │
  │   profile: { display_name, family_role, ... } │
  │   family: { info, members }                   │
  │   agents: { available, myConfigs, agentTypes } │
  │   permissions: [...]                           │
  │   conversations: { items, nextCursor }         │
  └──────────────────┬───────────────────────────┘
                     │
        Consumed by every screen via useSession()
                     │
    ┌────────────────┼────────────────────┐
    │                │                    │
ChatScreen    MyAgentsScreen    AdminPanel
(reads convs)  (reads agents,   (reads agents,
               permissions)     members)
```

### Individual Refresh Actions

After bootstrap, screens can refresh specific slices of state:

| Action | API Call | Updates |
|--------|----------|---------|
| `refreshAgents()` | `GET /api/agents/available` + `GET /api/agents/my` | `agents.available` + `agents.myConfigs` |
| `refreshPermissions()` | `GET /api/permissions` | `permissions` |
| `refreshProfile()` | `GET /api/profiles/me` | `profile` |
| `refreshFamily()` | `GET /api/family` | `family` |
| `refreshConversations()` | `GET /api/conversations` | `conversations` |

**MyAgentsScreen** auto-refreshes agents on screen focus (via navigation listener) and supports pull-to-refresh. This means changes made by the admin (authorizing agents) are reflected without restarting the app.

### Optimistic UI Updates

Permission toggles use optimistic updates for instant feedback:

```
User toggles permission ON
  │
  ├─> Immediately: setLocalPermissionOverrides({health_data: 'active'})
  │   → UI shows "Granted" instantly
  │
  ├─> API call: PUT /api/permissions/health_data
  │
  ├─> On success: refreshPermissions() → clears local overrides
  │   → UI shows server-confirmed state
  │
  └─> On error: Alert + refreshPermissions()
      → UI reverts to actual server state
```

---

## 11. Authentication Flow

### Dual-Strategy Auth

Every API request goes through the same auth pipeline:

```
Request arrives with Authorization: Bearer <token>
                    │
                    ▼
          ┌─────────────────┐
          │ Is Cognito       │
          │ configured?      │
          └────┬────────┬───┘
               │YES     │NO
               ▼        │
    ┌──────────────────┐ │
    │ Try Cognito JWT  │ │
    │ verification     │ │
    └──┬───────────┬───┘ │
       │VALID      │FAIL │
       ▼           ▼     ▼
  Set g.user  ┌──────────────────┐
  from sub    │ Try device token │
  claim       │ lookup in Devices│
              │ table (GSI)      │
              └──┬───────────┬───┘
                 │FOUND      │NOT FOUND
                 ▼           ▼
           Set g.user     Return 401
           from record    Unauthorized
```

**Key:** Both strategies result in the same `g.user_id`, `g.user_name`, `g.family_id` being set on the Flask `g` object. Downstream code doesn't know or care which auth method was used.

### Token Storage on Mobile
- **Device token**: Stored in `expo-secure-store` (encrypted, persists across app restarts)
- **Cognito tokens**: Stored in `expo-secure-store` (access token + refresh token)
- On each API call, `api.ts` reads the token from secure store and adds the `Authorization` header

### Auth Expiration
- When any API call returns 401, an event is emitted via `authEvents.ts`
- `AppNavigator.tsx` listens for this event and navigates back to the Register screen
- The session is cleared (`dispatch({type: 'SESSION_CLEAR'})`)

---

## 12. Family & Permissions Model

### Family Structure

```
┌─────────────────────────────────────────────────┐
│                   FAMILY                         │
│  family_id: "fam_01ABC..."                      │
│  family_name: "The Smith Family"                │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │  Admin   │  │  Member  │  │  Member  │      │
│  │  (Dad)   │  │  (Mom)   │  │  (Henry) │      │
│  │  owner   │  │  admin   │  │  member  │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       │              │              │            │
│       │         Family Tree         │            │
│       │    (FamilyRelationships)    │            │
│       │                             │            │
│       └──── spouse ────┘            │            │
│             parent ─────────────────┘            │
│                                                  │
└─────────────────────────────────────────────────┘
```

### Roles
- **owner** — Created the family. Full admin powers. Cannot be removed.
- **admin** — Can manage members, authorize agents, view health reports. Multiple admins allowed.
- **member** — Standard user. Can chat, manage own agents and permissions.

### Family Context in System Prompt
When a member chats with Claude, the system prompt is enriched with:
- The member's profile (name, family role, health notes, interests)
- Family member list (names and roles)
- Family tree relationships ("Henry is the child of Dad and Mom")

This allows Claude to give contextual responses like "Since your father mentioned being allergic to shellfish..." without the user having to repeat family information.

### The Permission Model

```
┌────────────────────────────────────────────────────────────┐
│  ADMIN LAYER (coarse-grained)                               │
│                                                              │
│  Admin controls WHICH AGENTS a member can access             │
│  via AgentConfigs table                                      │
│                                                              │
│  Example: Admin enables Health Advisor for Henry             │
│           Admin does NOT enable Logistics for Henry          │
│           → Henry can only see Health Advisor in My Agents   │
└──────────────────────────┬─────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────────┐
│  MEMBER LAYER (fine-grained)                                │
│                                                              │
│  Member controls WHAT DATA agents can access                 │
│  via MemberPermissions table                                 │
│                                                              │
│  Example: Henry enables Health Advisor (toggle ON)           │
│           Henry grants health_data permission                │
│           Henry does NOT grant medical_records               │
│           → Health Advisor can read observations             │
│             but NOT medical documents                         │
└────────────────────────────────────────────────────────────┘
```

### Permission Types and What They Gate

| Permission | What It Allows | Required By |
|-----------|----------------|-------------|
| `health_data` | Read/write health observations, records, vitals | Health Advisor |
| `medical_records` | Access uploaded medical documents (PDFs, images in S3) | Health Advisor |
| `email_access` | Read/draft emails on behalf of the member | Logistics Assistant |
| `calendar_access` | Access calendar events and scheduling | Logistics Assistant |

### The Grant/Revoke Flow

```
Member opens My Agents
  → Taps Health Advisor (expands)
  → Sees: "Health Data Access: Not granted" with toggle
  → Toggles ON
     │
     ├─ Optimistic UI: shows "Granted" immediately
     │
     ├─ API: PUT /api/permissions/health_data
     │        body: {config: {consent_given: true, data_sources: ["healthkit"]}}
     │
     ├─ Backend: Creates MemberPermissions record
     │           {user_id, permission_type: "health_data", status: "active", config: {...}}
     │
     └─ Refresh: GET /api/permissions → updates SessionContext

To revoke:
  → Toggles OFF
     │
     ├─ API: DELETE /api/permissions/health_data
     │
     └─ Backend: Removes MemberPermissions record
                 → Agent can no longer access health data
```

**Special case — email_access:** When the member tries to grant email access, the app redirects them to the Agent Setup screen (`AgentSetupScreen.tsx`) where they configure their email credentials first. This is because email access requires account-specific configuration, not just a consent toggle.

---

## Summary

HomeAgent is a family AI platform with three core loops:

1. **Chat Loop**: Member → types/speaks → API → Claude (with agent orchestration) → streaming response → auto health extraction
2. **Agent Loop**: Admin authorizes → member enables → member grants permissions → agent becomes available in chat
3. **Health Loop**: Manual entry + auto-extraction → stored in DynamoDB → queried by Health Advisor → summarized in reports

Everything is glued together by the **session bootstrap** (one API call loads all state) and the **2-layer permission model** (admin controls access, member controls data). The mobile app is the primary interface, with real-time streaming for both text and voice interactions.
