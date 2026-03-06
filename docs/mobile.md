# HomeAgent Mobile App -- Engineering Documentation

## 1. Architecture Overview

### Framework and Tooling

- **Expo managed workflow**, SDK 52 (expo ^54.0.0, React Native 0.81.5, React 19.1.0)
- **TypeScript strict mode** (`"strict": true` in tsconfig.json, extends `expo/tsconfig.base`)
- Path alias: `@/*` maps to `src/*`
- New Architecture enabled (`"newArchEnabled": true` in app.json)
- Portrait only, light UI style

### Project Structure

```
mobile/
  App.tsx                          # Root: SafeAreaProvider + StatusBar + AppNavigator
  app.json                         # Expo config (plugins, permissions, apiBaseUrl)
  tsconfig.json                    # Strict TS, path aliases
  src/
    navigation/
      AppNavigator.tsx             # Stack navigator, session bootstrap, auth listener
    store/
      index.ts                     # Re-exports SessionProvider, useSession, types
      SessionContext.tsx            # React Context + useReducer state management
      useSession.ts                # Hook: actions (bootstrap, refresh*, logout, etc.)
    screens/
      RegisterScreen.tsx           # Auth: signup, login, invite-code registration
      ConversationListScreen.tsx   # Home: conversation list (FlatList)
      ChatScreen.tsx               # Chat: SSE streaming, images, voice-to-chat
      SettingsScreen.tsx            # Account info, links to profile/admin
      ProfileScreen.tsx            # Edit own profile
      MyAgentsScreen.tsx           # Member agent self-service
      AdminPanelScreen.tsx         # Admin hub
      AdminMembersScreen.tsx       # List all member profiles
      AdminMemberDetailScreen.tsx  # Edit member profile + agent authorization
      FamilyManageScreen.tsx       # Create family, invite members, manage invites
      FamilyTreeScreen.tsx         # Set relationships between members
      AgentSetupScreen.tsx         # Post-registration permission setup
      VoiceModeScreen.tsx          # WebSocket voice mode (Nova Sonic)
      AdminAgentTemplatesScreen.tsx # CRUD agent templates (not in navigator)
    services/
      api.ts                       # All HTTP API functions, base URL, auth headers
      auth.ts                      # Device token storage (expo-secure-store)
      cognitoAuth.ts               # Cognito signup/login, token storage
      sse.ts                       # SSE streaming via XMLHttpRequest
      voiceSession.ts              # WebSocket client for voice mode
      chatMedia.ts                 # Image/audio upload via S3 presigned URLs
      authEvents.ts                # Auth expiration event bus
    components/
      ChatInput.tsx                # Text input + image picker + voice record button
      MessageBubble.tsx            # Chat message display (text + images)
      ConversationItem.tsx         # Single conversation row in list
      ImageAttachment.tsx          # Thumbnail preview with remove/status overlay
      VoiceButton.tsx              # Mic button (idle/recording states)
    types/
      index.ts                     # All shared TypeScript interfaces
```

### Key Dependencies

| Package | Purpose |
|---------|---------|
| `@react-navigation/native` + `native-stack` v7 | Navigation |
| `expo-secure-store` | Encrypted token storage |
| `expo-av` | Audio recording and playback |
| `expo-image-picker` | Image attachment selection |
| `expo-file-system` | File read (base64 encoding for voice) |
| `expo-constants` | Access `app.json` extra config |
| `react-native-safe-area-context` | Safe area insets |

---

## 2. Navigation

### AppNavigator

**File:** `/home/ubuntu/homeagent/mobile/src/navigation/AppNavigator.tsx`

The root component tree is:

```
App (App.tsx)
  SafeAreaProvider
    StatusBar
    AppNavigator
      SessionProvider           -- wraps all screens with context
        AppContent              -- bootstrap + conditional rendering
          NavigationContainer
            Stack.Navigator
```

`AppContent` calls `actions.bootstrap()` on mount. While `session.status === 'loading'`, a splash screen (title + spinner) is shown. Once resolved:

- `authenticated` --> initial route is `ConversationList`
- `unauthenticated` --> initial route is `Register`

### RootStackParamList

```typescript
export type RootStackParamList = {
  Register: undefined;
  ConversationList: undefined;
  Chat: { conversationId?: string; title?: string };
  Settings: undefined;
  Profile: undefined;
  AdminMembers: undefined;
  AdminMemberDetail: { userId: string };
  FamilyTree: undefined;
  AdminPanel: undefined;
  FamilyManage: undefined;
  MyAgents: undefined;
  AgentSetup: undefined;
  VoiceMode: { conversationId?: string };
};
```

All screens are registered in a single `Stack.Navigator` (no tab navigation). The `Register` screen has `headerShown: false`; `VoiceMode` also has `headerShown: false` (dark themed full-screen).

### Auth Expiration Listener

`AppContent` subscribes to `onAuthExpired` (from `authEvents.ts`). When any API call returns 401, the listener fires, calls `actions.logout()`, shows an Alert, and resets navigation to `Register`.

---

## 3. State Management

### SessionContext + useReducer

**File:** `/home/ubuntu/homeagent/mobile/src/store/SessionContext.tsx`

A single `React.createContext` holds the entire app state. `SessionProvider` wraps the app at the navigator level.

#### SessionState Shape

```typescript
interface SessionState {
  status: 'loading' | 'authenticated' | 'unauthenticated';
  user: SessionUser | null;
  profile: MemberProfile | null;
  family: {
    info: Family;
    members: FamilyMember[];
  } | null;
  agents: {
    available: AvailableAgent[];
    myConfigs: AgentConfig[];
    agentTypes: Record<string, AgentTypeInfo>;
  };
  permissions: PermissionGrant[];
  conversations: {
    items: Conversation[];
    nextCursor?: string;
    lastFetched: number | null;
  };
}
```

```typescript
interface SessionUser {
  userId: string;
  name: string;
  email: string;
  role: 'admin' | 'member' | 'owner';
}
```

#### Initial State

```typescript
const initialState: SessionState = {
  status: 'loading',
  user: null,
  profile: null,
  family: null,
  agents: { available: [], myConfigs: [], agentTypes: {} },
  permissions: [],
  conversations: { items: [], nextCursor: undefined, lastFetched: null },
};
```

#### Action Types

| Action | Payload | Effect |
|--------|---------|--------|
| `SESSION_BOOTSTRAP` | Full session data | Sets status to `authenticated`, populates all fields, records `lastFetched` |
| `SESSION_CLEAR` | none | Resets to `initialState` with status `unauthenticated` |
| `UPDATE_PROFILE` | `MemberProfile` | Replaces `profile` |
| `UPDATE_FAMILY` | `{info, members} \| null` | Replaces `family` |
| `UPDATE_AGENTS` | `{available, myConfigs}` | Merges into `agents` |
| `UPDATE_PERMISSIONS` | `PermissionGrant[]` | Replaces `permissions` |
| `SET_CONVERSATIONS` | `{items, nextCursor?}` | Replaces conversations, updates `lastFetched` |
| `ADD_CONVERSATION` | `Conversation` | Prepends to list (deduplicating by ID) |
| `REMOVE_CONVERSATION` | `string` (conversation_id) | Filters out from list |

### useSession Hook

**File:** `/home/ubuntu/homeagent/mobile/src/store/useSession.ts`

```typescript
interface UseSessionReturn {
  session: SessionState;
  actions: {
    bootstrap: () => Promise<void>;
    logout: () => Promise<void>;
    refreshProfile: () => Promise<void>;
    updateProfile: (updates: Partial<Pick<MemberProfile, ...>>) => Promise<MemberProfile>;
    refreshFamily: () => Promise<void>;
    refreshAgents: () => Promise<void>;
    refreshPermissions: () => Promise<void>;
    refreshConversations: () => Promise<void>;
    addConversation: (conv: Conversation) => void;
    removeConversation: (id: string) => void;
  };
  isOwnerOrAdmin: boolean;
}
```

#### Session Bootstrap Flow

`bootstrap()` makes a **single API call** to `GET /api/session` which returns `SessionBootstrapResponse`. This includes user info, profile, family, agents (available + my_configs + agent_types), permissions, and recent conversations. On success it dispatches `SESSION_BOOTSTRAP`; on failure it dispatches `SESSION_CLEAR`.

#### Logout

Clears the device token from secure store, clears Cognito tokens (dynamically imported), and dispatches `SESSION_CLEAR`.

#### Key Detail: `isOwnerOrAdmin`

A `useMemo` derived boolean: `role === 'owner' || role === 'admin'`. Used by `SettingsScreen` to conditionally show the Admin Panel link.

---

## 4. Screens

### RegisterScreen

**File:** `/home/ubuntu/homeagent/mobile/src/screens/RegisterScreen.tsx`
**Route:** `Register` (no params)

A multi-mode registration screen controlled by `mode: 'select' | 'owner' | 'member' | 'confirm' | 'login'`.

**Mode: `select`** (default) -- Landing page with three options:
- "Create Family" --> switches to `owner` mode
- "Join Family" --> switches to `member` mode
- "Already have an account? Sign In" --> switches to `login` mode

**Mode: `owner`** -- Cognito signup flow:
- Fields: email, display name, password, confirm password
- Validates password >= 8 chars, passwords match
- Calls `signUp()` from `cognitoAuth.ts`
- On success, transitions to `confirm` mode

**Mode: `confirm`** -- Email verification:
- Field: 6-digit verification code
- Calls `confirmSignUp()` then auto-logs in with `signIn()`
- Stores Cognito tokens in secure store
- Calls `actions.bootstrap()` then navigates to `ConversationList`
- "Resend Code" button available

**Mode: `login`** -- Returning user sign-in:
- Fields: email, password
- Calls `signIn()` from `cognitoAuth.ts`
- Calls `actions.bootstrap()` then navigates to `ConversationList`

**Mode: `member`** -- Invite code registration:
- Fields: invite code (6 chars, auto-uppercased), display name
- Calls `register()` API with device info (platform auto-detected)
- Saves `device_token` to secure store
- Calls `actions.bootstrap()` then navigates to `AgentSetup`

All modes use `navigation.reset()` to clear the back stack after successful auth.

---

### ConversationListScreen (HomeScreen)

**File:** `/home/ubuntu/homeagent/mobile/src/screens/ConversationListScreen.tsx`
**Route:** `ConversationList` (no params)

**Key state:** `refreshing` (boolean)

**Behavior:**
- Reads conversations from `session.conversations.items` (not local fetch -- uses the store)
- **Stale refresh on focus:** Listens for `focus` event; if `lastFetched` is null or > 30 seconds ago, calls `actions.refreshConversations()`
- **Pull-to-refresh:** Triggers `actions.refreshConversations()`
- **Tap conversation:** Navigates to `Chat` with `conversationId` and `title`
- **Long-press conversation:** Confirm dialog to delete (calls `deleteConversation()` API then `actions.removeConversation()`)
- **FAB "+":** Navigates to `Chat` with empty params (new conversation)
- **Header right:** "Settings" text button --> navigates to `Settings`

---

### ChatScreen

**File:** `/home/ubuntu/homeagent/mobile/src/screens/ChatScreen.tsx`
**Route:** `Chat` with params `{ conversationId?: string; title?: string }`

**Key state:**
- `messages: DisplayMessage[]` -- local array of `{ id, role, content, localImages? }`
- `currentConversationId: string | null`
- `streaming: boolean` -- disables input during stream
- `loadingMessages: boolean`
- `loadError: string | null`

**Message loading:**
- If `conversationId` param provided: loads messages for that conversation
- If no param: fetches most recent conversation (`getConversations(1)`), loads its messages, sets as current
- If no conversations exist: starts fresh (empty screen)

**Sending a message:**
1. Adds user message to local `messages` immediately (optimistic)
2. Uploads any image/audio attachments via `uploadImage()` (S3 presigned URL)
3. Adds empty assistant message placeholder
4. Calls `streamChat()` which opens XHR to `POST /api/chat` with SSE
5. On `text_delta` events: appends content to assistant message
6. On `message_done`: updates `currentConversationId`, calls `actions.addConversation()` if new
7. On `error`: replaces assistant message content with error text
8. AbortController allows cancelling on unmount

**Header:** Title from params or "HomeAgent"; settings gear icon on right.

---

### SettingsScreen

**File:** `/home/ubuntu/homeagent/mobile/src/screens/SettingsScreen.tsx`
**Route:** `Settings` (no params)

Displays:
- **ACCOUNT section:** Name, User ID, Role (read-only from session)
- **PROFILE section:**
  - "Edit My Profile" --> navigates to `Profile`
  - "My Agents" --> navigates to `MyAgents`
- **ADMIN section (conditional):** Only shown when `isOwnerOrAdmin` is true
  - "Open Admin Panel" button --> navigates to `AdminPanel`
- **Log Out button:** Confirmation alert, calls `actions.logout()`, resets to `Register`
- **Version:** Reads from `expo-constants` (`expoConfig.version`)

---

### ProfileScreen

**File:** `/home/ubuntu/homeagent/mobile/src/screens/ProfileScreen.tsx`
**Route:** `Profile` (no params)

**Key state:** `saving`, `displayName`, `familyRole`, `healthNotes`, `interestsText`

Fields are pre-populated from `session.profile` via `useEffect`. Editable fields:
- Display Name (text)
- Family Role (text, e.g., "Parent, Child, Grandparent")
- Health Notes (multiline)
- Interests (comma-separated text, parsed to string array on save)

Calls `actions.updateProfile()` which hits `PUT /api/profiles/me` and updates the store.

Shows read-only Role and User ID at bottom.

---

### MyAgentsScreen

**File:** `/home/ubuntu/homeagent/mobile/src/screens/MyAgentsScreen.tsx`
**Route:** `MyAgents` (no params)

**Key state:**
- `toggling: string | null` -- agent_type currently being toggled
- `expandedAgent: string | null` -- which agent's permission panel is open
- `refreshing: boolean`
- `localPermissionOverrides: Record<string, 'active' | 'revoked'>` -- for optimistic UI

**Two-layer authorization model:**
1. Admin authorizes agents per member (creates `AgentConfig` records)
2. Member can only see and toggle agents that admin has authorized

The screen filters `session.agents.available` to only those whose `agent_type` exists in `session.agents.myConfigs`.

**Agent list (FlatList):**
- Each agent shows name, description, built-in badge, and a `Switch` toggle
- Tapping a row expands the permissions panel (if the agent has `required_permissions`)
- Collapsed state shows a summary: "All permissions granted" or "N permissions needed"
- Expanded panel shows each required permission with a label and a `Switch`

**Agent toggle:** Calls `enableMyAgent()` or `disableMyAgent()`, then `actions.refreshAgents()`.

**Permission toggle:**
- Revoking: calls `revokePermission()`, applies optimistic override, then `actions.refreshPermissions()`
- Granting `email_access`: redirects to `AgentSetup` screen instead of directly granting
- Granting other types: uses hardcoded default configs, calls `grantPermission()`, optimistic update, then refresh

**Auto-refresh on focus:** Calls `actions.refreshAgents()` when screen gains focus.
**Pull-to-refresh:** Triggers `actions.refreshAgents()`.

**Empty state:** Message explaining that the admin hasn't authorized any agents yet.

---

### AdminPanelScreen

**File:** `/home/ubuntu/homeagent/mobile/src/screens/AdminPanelScreen.tsx`
**Route:** `AdminPanel` (no params)

A navigation hub for admin features. Sections:

**FAMILY MANAGEMENT:**
- "Family Members" --> `AdminMembers` (view/manage profiles)
- "Family Tree" --> `FamilyTree` (manage relationships)
- "Family & Invites" --> `FamilyManage` (manage family, send invites)
- "Generate Invite Code" --> calls `generateInviteCode()` API, shows code in Alert

**AGENT MANAGEMENT:**
- "Agent Configurations" --> `AdminMembers` (enable/disable agents per member)

**SYSTEM:**
- "System Info" -- static text noting agent templates are managed via Debug Console

---

### AdminMembersScreen

**File:** `/home/ubuntu/homeagent/mobile/src/screens/AdminMembersScreen.tsx`
**Route:** `AdminMembers` (no params)

**Key state:** `profiles: MemberProfile[]`, `loading: boolean`

- Verifies admin/owner role from session (shows "Access denied" otherwise)
- Calls `listProfiles()` on mount and on every focus
- Renders a `FlatList` of members showing display_name, family_role, and role
- Tapping a member navigates to `AdminMemberDetail` with `{ userId }`

---

### AdminMemberDetailScreen

**File:** `/home/ubuntu/homeagent/mobile/src/screens/AdminMemberDetailScreen.tsx`
**Route:** `AdminMemberDetail` with params `{ userId: string }`

**Key state:** `profile`, `agentConfigs: AgentConfig[]`, `loading`, `saving`, `deleting`, `familyRole`, `healthNotes`

On mount, loads profile and agent configs in parallel (`Promise.all`).

**Sections:**
- **MEMBER INFO:** Read-only name and role
- **PROFILE:** Editable family role and health notes, "Save Profile" button (calls `updateProfile()` admin API)
- **AI AGENTS:** Iterates over `session.agents.agentTypes` (all known agent types) and renders a `Switch` for each. Toggling on calls `putAgentConfig(userId, agentType, {enabled: true})`; toggling off calls `deleteAgentConfig()`. This is the admin-side of the two-layer auth system.
- **DANGER ZONE (conditional):** Only shown if `userId !== session.user?.userId`. "Remove Member" button with destructive confirmation. Calls `deleteMember()`, navigates back on success.

---

### FamilyManageScreen

**File:** `/home/ubuntu/homeagent/mobile/src/screens/FamilyManageScreen.tsx`
**Route:** `FamilyManage` (no params)

**Key state:** `invites: FamilyInvite[]`, `loadingInvites`, `inviteEmail`, `inviting`, `showInviteInput`, `familyName`, `creatingFamily`

**No family state:** Shows a "Create Family" form (name input + button). Calls `createFamily()`, then `actions.refreshFamily()`.

**Has family state:**
- **Family info header:** Family name, member count
- **MEMBERS section:** FlatList of `session.family.members` (name + role)
- **INVITE MEMBER section:** Toggle-able email input. Calls `inviteMember(email)`. If `email_sent` is false in the response, shows the invite code for manual sharing.
- **PENDING INVITES section:** Lists invites with email/code. Each has a "Cancel" button that calls `cancelInvite()`.

---

### FamilyTreeScreen

**File:** `/home/ubuntu/homeagent/mobile/src/screens/FamilyTreeScreen.tsx`
**Route:** `FamilyTree` (no params)

**Key state:** `members: MemberProfile[]`, `relationshipMap: Record<string, RelationshipType>`, `pickerMember`, `savingFor`

On mount, loads all profiles (excluding self) and the current user's relationships.

**Relationship types:** `parent_of | child_of | spouse_of | sibling_of`

**UI:** FlatList of members. Each row shows the member name and current relationship label. Tapping opens a modal bottom sheet with options:
- No relationship
- My child (`parent_of`)
- My parent (`child_of`)
- My spouse / partner (`spouse_of`)
- My sibling (`sibling_of`)

Selecting an option calls `deleteRelationship()` (if changing) then `createRelationship()`. Updates local `relationshipMap` optimistically.

---

### AgentSetupScreen

**File:** `/home/ubuntu/homeagent/mobile/src/screens/AgentSetupScreen.tsx`
**Route:** `AgentSetup` (no params)

A post-registration onboarding screen for configuring agent permissions. Shown after member invite-code registration.

**Logistics Assistant section:**
- Email address (text input)
- Email provider (segmented: Gmail / Outlook / Other)
- Calendar access (Switch)

**Health Advisor section:**
- Health data access (Switch -- HealthKit consent)
- Medical records access (Switch)

**Actions:**
- "Continue" -- Grants selected permissions via `grantPermission()` API calls, then navigates to `ConversationList`
- "Skip for now" -- Navigates directly to `ConversationList`

---

### VoiceModeScreen

**File:** `/home/ubuntu/homeagent/mobile/src/screens/VoiceModeScreen.tsx`
**Route:** `VoiceMode` with params `{ conversationId?: string }`

**Key state:** `connected`, `recording`, `speaking`, `transcripts: Transcript[]`, `error`

Dark-themed full-screen voice interface.

**Connection:** On mount, creates `VoiceSessionClient`, connects via WebSocket, sends `audio_start`. Disconnects on unmount.

**Recording:** Uses `expo-av` `Audio.Recording` with 16kHz mono WAV format. On stop, reads file as base64, sends `audio_chunk` then `audio_end` via WebSocket.

**Playback:** Incoming `audio_chunk` events are queued. Sequential playback using `Audio.Sound.createAsync` with data URIs. `speaking` state tracks playback.

**Transcripts:** `transcript` events are displayed in a ScrollView with user/assistant role styling.

**Controls:**
- Status text: "Connecting..." / "Listening..." / "Speaking..." / "Tap to speak"
- Large mic button: Blue (idle), Red (recording), Gray (disconnected)
- "Back to Chat" link

---

### AdminAgentTemplatesScreen

**File:** `/home/ubuntu/homeagent/mobile/src/screens/AdminAgentTemplatesScreen.tsx`
**Route:** Not registered in `AppNavigator` (standalone screen, possibly used from web debug console)

CRUD interface for agent templates. FlatList of templates with modal form for create/edit. Supports deleting non-builtin templates.

---

## 5. Services Layer

### api.ts

**File:** `/home/ubuntu/homeagent/mobile/src/services/api.ts`

#### Base URL Resolution

```typescript
function getBaseUrl(): string
```

Priority:
1. `Constants.expoConfig?.extra?.apiBaseUrl` (from app.json)
2. In `__DEV__` mode: extracts host IP from `Constants.expoConfig?.hostUri`, port 5000; falls back to `10.0.2.2:5000` (Android emulator) or `localhost:5000` (iOS simulator)
3. Production fallback: `https://api.example.com`

#### Auth Headers

```typescript
async function headers(): Promise<Record<string, string>>
```

Prefers Cognito access token (dynamically imported from `cognitoAuth.ts`) over device token. Always includes `Content-Type: application/json` and `bypass-tunnel-reminder: true`.

#### Request Helpers

- `request<T>(path, options)` -- Authenticated request. On 401, calls `emitAuthExpired()`. Throws on non-OK responses.
- `publicRequest<T>(path, options)` -- Unauthenticated request (no Authorization header). Used for signup/login/confirm.

#### API Functions

**Auth:**
| Function | Method | Path | Auth |
|----------|--------|------|------|
| `register(data: RegisterRequest)` | POST | `/api/auth/register` | Yes |
| `cognitoSignUp(data: SignupRequest)` | POST | `/api/auth/signup` | No |
| `cognitoConfirm(data: ConfirmRequest)` | POST | `/api/auth/confirm` | No |
| `cognitoLogin(data: LoginRequest)` | POST | `/api/auth/login` | No |
| `cognitoResendCode(data: ResendCodeRequest)` | POST | `/api/auth/resend-code` | No |
| `verify()` | POST | `/api/auth/verify` | Yes |
| `getSession()` | GET | `/api/session` | Yes |

**Conversations:**
| Function | Method | Path |
|----------|--------|------|
| `getConversations(limit?, cursor?)` | GET | `/api/conversations?limit=N&cursor=X` |
| `getMessages(conversationId, limit?, cursor?)` | GET | `/api/conversations/:id/messages?...` |
| `deleteConversation(conversationId)` | DELETE | `/api/conversations/:id` |

**Profiles:**
| Function | Method | Path |
|----------|--------|------|
| `getMyProfile()` | GET | `/api/profiles/me` |
| `updateMyProfile(updates)` | PUT | `/api/profiles/me` |
| `listProfiles()` | GET | `/api/admin/profiles` |
| `getProfile(userId)` | GET | `/api/admin/profiles/:userId` |
| `updateProfile(userId, updates)` | PUT | `/api/admin/profiles/:userId` |
| `deleteMember(userId)` | DELETE | `/api/admin/profiles/:userId` |

**Agents (Admin):**
| Function | Method | Path |
|----------|--------|------|
| `getAgentTypes()` | GET | `/api/admin/agents/types` |
| `getAgentConfigs(userId)` | GET | `/api/admin/agents/:userId` |
| `putAgentConfig(userId, agentType, data)` | PUT | `/api/admin/agents/:userId/:agentType` |
| `deleteAgentConfig(userId, agentType)` | DELETE | `/api/admin/agents/:userId/:agentType` |

**Agent Templates (Admin):**
| Function | Method | Path |
|----------|--------|------|
| `listAgentTemplates()` | GET | `/api/admin/agent-templates` |
| `createAgentTemplate(data)` | POST | `/api/admin/agent-templates` |
| `updateAgentTemplate(templateId, data)` | PUT | `/api/admin/agent-templates/:id` |
| `deleteAgentTemplate(templateId)` | DELETE | `/api/admin/agent-templates/:id` |

**Agents (Member Self-Service):**
| Function | Method | Path |
|----------|--------|------|
| `getAvailableAgents()` | GET | `/api/agents/available` |
| `getMyAgents()` | GET | `/api/agents/my` |
| `enableMyAgent(agentType)` | PUT | `/api/agents/my/:agentType` |
| `disableMyAgent(agentType)` | DELETE | `/api/agents/my/:agentType` |

**Permissions:**
| Function | Method | Path |
|----------|--------|------|
| `getMyPermissions()` | GET | `/api/permissions` |
| `grantPermission(permissionType, config)` | PUT | `/api/permissions/:type` |
| `revokePermission(permissionType)` | DELETE | `/api/permissions/:type` |
| `getRequiredPermissions(agentType)` | GET | `/api/permissions/agent-required/:agentType` |

**Family:**
| Function | Method | Path |
|----------|--------|------|
| `createFamily(name)` | POST | `/api/family` |
| `getFamily()` | GET | `/api/family` |
| `inviteMember(email)` | POST | `/api/family/invite` |
| `getPendingInvites()` | GET | `/api/family/invites` |
| `cancelInvite(code)` | DELETE | `/api/family/invites/:code` |
| `generateInviteCode()` | POST | `/api/admin/invite-codes` |

**Family Relationships:**
| Function | Method | Path |
|----------|--------|------|
| `getFamilyRelationships()` | GET | `/api/admin/family/relationships` |
| `getUserRelationships(userId)` | GET | `/api/admin/family/relationships/:userId` |
| `createRelationship(userId, relatedUserId, type)` | POST | `/api/admin/family/relationships` |
| `deleteRelationship(userId, relatedUserId)` | DELETE | `/api/admin/family/relationships/:u1/:u2` |

**Chat Media:**
| Function | Method | Path |
|----------|--------|------|
| `uploadChatImage(contentType, fileSize)` | POST | `/api/chat/upload-image` |

**Voice:**
| Function | Returns |
|----------|---------|
| `buildVoiceWsUrl(conversationId)` | WebSocket URL: `ws[s]://host/api/voice?token=...&conversation_id=...` |

---

### auth.ts

**File:** `/home/ubuntu/homeagent/mobile/src/services/auth.ts`

Uses `expo-secure-store` with key `homeagent_device_token`.

```typescript
saveToken(token: string): Promise<void>
getToken(): Promise<string | null>
clearToken(): Promise<void>   // Also clears Cognito tokens
```

---

### cognitoAuth.ts

**File:** `/home/ubuntu/homeagent/mobile/src/services/cognitoAuth.ts`

Wraps the Cognito auth API calls and manages three tokens in secure store:

| Key | Purpose |
|-----|---------|
| `homeagent_cognito_access_token` | Used in Authorization headers |
| `homeagent_cognito_id_token` | Stored but not directly used by mobile |
| `homeagent_cognito_refresh_token` | Stored but not directly used by mobile |

Functions:

```typescript
signUp(email, password, displayName): Promise<SignupResponse>
confirmSignUp(email, code): Promise<boolean>
signIn(email, password): Promise<LoginResponse>   // Stores all 3 tokens
resendCode(email): Promise<boolean>
getCognitoAccessToken(): Promise<string | null>
getCognitoIdToken(): Promise<string | null>
clearCognitoTokens(): Promise<void>
```

**Token priority:** `api.ts` headers prefer Cognito access token over device token. The Cognito module is dynamically imported (`await import('./cognitoAuth')`) with try/catch so the app works if the module is unavailable.

---

### sse.ts

**File:** `/home/ubuntu/homeagent/mobile/src/services/sse.ts`

```typescript
streamChat(
  message: string,
  conversationId: string | null,
  onEvent: (event: SSEEvent) => void,
  onError: (error: Error) => void,
  signal?: AbortSignal,
  media?: string[],
): Promise<void>
```

Uses `XMLHttpRequest` (not fetch) because React Native's fetch does not reliably support `ReadableStream`. XHR's `onprogress` fires as SSE chunks arrive. Parses `data: {...}` lines from the response text.

Request body: `{ message, conversation_id?, media? }`
Headers: JSON content type, Bearer auth, Accept `text/event-stream`.

On 401 response, calls `emitAuthExpired()`.

---

### voiceSession.ts

**File:** `/home/ubuntu/homeagent/mobile/src/services/voiceSession.ts`

```typescript
class VoiceSessionClient {
  constructor(conversationId: string | null, onEvent: (e: VoiceEvent) => void, onClose: () => void)
  connect(): Promise<void>
  sendAudioStart(config?: { sample_rate: number }): void
  sendAudioChunk(base64Pcm: string): void
  sendAudioEnd(): void
  sendText(content: string): void
  disconnect(): void
}
```

WebSocket client for bidirectional voice streaming with Amazon Nova Sonic. Messages are JSON-encoded. The `connect()` method builds the WebSocket URL via `buildVoiceWsUrl()` which includes the auth token as a query parameter.

---

### chatMedia.ts

**File:** `/home/ubuntu/homeagent/mobile/src/services/chatMedia.ts`

```typescript
uploadImage(uri: string, contentType: string, fileSize: number): Promise<string>  // returns media_id
uploadAudio(uri: string, fileSize: number): Promise<string>  // returns media_id, hardcoded audio/wav
getContentType(uri: string): string  // extension-based MIME lookup
```

Two-step upload process:
1. `POST /api/chat/upload-image` to get `{ media_id, upload_url }` (presigned S3 URL)
2. `PUT` the file binary to the presigned URL using `expo-file-system`'s `uploadAsync`

---

### authEvents.ts

**File:** `/home/ubuntu/homeagent/mobile/src/services/authEvents.ts`

Simple pub-sub event bus for auth expiration:

```typescript
onAuthExpired(listener: () => void): () => void    // subscribe, returns unsubscribe fn
emitAuthExpired(): void                             // fires all listeners, debounced (1s)
```

The `firing` guard prevents re-entrant calls within a 1-second window.

---

## 6. Types

**File:** `/home/ubuntu/homeagent/mobile/src/types/index.ts`

### Core Domain Types

```typescript
interface User {
  user_id: string;
  name: string;
  role: 'admin' | 'member' | 'owner';
}

interface Conversation {
  conversation_id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

interface MediaInfo {
  media_id: string;
  content_type: string;
}

interface Message {
  conversation_id: string;
  sort_key: string;
  message_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  model?: string;
  tokens_used?: number;
  media?: MediaInfo[];
}

interface ChatMediaUpload {
  localId: string;
  uri: string;
  contentType: string;
  fileSize: number;
  mediaId?: string;
  status: 'pending' | 'uploading' | 'uploaded' | 'error';
}
```

### Profile and Family

```typescript
interface MemberProfile {
  user_id: string;
  display_name: string;
  family_role: string;
  preferences: Record<string, string>;
  health_notes: string;
  interests: string[];
  role: 'admin' | 'member' | 'owner';
  created_at: string;
  updated_at: string;
}

interface Family {
  family_id: string;
  name: string;
  owner_user_id: string;
  created_at: string;
}

interface FamilyMember {
  family_id: string;
  user_id: string;
  role: 'owner' | 'member';
  joined_at: string;
  name: string;
}

interface FamilyInvite {
  code: string;
  created_by: string;
  status: string;
  invited_email?: string;
  family_id?: string;
  invite_type: 'email' | 'code';
  expires_at: string;
  created_at?: string;
}

type RelationshipType = 'parent_of' | 'child_of' | 'spouse_of' | 'sibling_of';

interface FamilyRelationship {
  user_id: string;
  related_user_id: string;
  relationship_type: RelationshipType;
  user_name?: string;
  related_user_name?: string;
  created_at: string;
}
```

### Agent System

```typescript
interface AgentConfig {
  user_id: string;
  agent_type: string;
  enabled: boolean;
  config: Record<string, unknown>;
  updated_at: string;
}

interface AgentTypeInfo {
  name: string;
  description: string;
  default_config: Record<string, unknown>;
  implemented: boolean;
  required_permissions?: PermissionType[];
  is_default?: boolean;
}

interface AgentTemplate {
  template_id: string;
  agent_type: string;
  name: string;
  description: string;
  system_prompt: string;
  default_config: Record<string, unknown>;
  required_permissions: PermissionType[];
  is_default: boolean;
  is_builtin: boolean;
  available_to: 'all' | string[];
  created_by: string;
  created_at: string;
  updated_at: string;
}

interface AvailableAgent extends AgentTemplate {
  enabled: boolean;
}
```

### Permissions

```typescript
type PermissionType = 'email_access' | 'calendar_access' | 'health_data' | 'medical_records';

interface PermissionGrant {
  user_id: string;
  permission_type: PermissionType;
  config: Record<string, unknown>;
  granted_at: string;
  granted_by: string;
  status: 'active' | 'revoked';
}

interface EmailAccessConfig {
  email_address: string;
  provider: 'gmail' | 'outlook' | 'other';
}

interface CalendarAccessConfig {
  calendar_id: string;
  provider: 'gmail' | 'outlook' | 'other';
}

interface HealthDataConfig {
  consent_given: boolean;
  data_sources: string[];
}

interface MedicalRecordsConfig {
  folder_path: string;
  s3_prefix: string;
}
```

### Auth Types

```typescript
interface CognitoTokens {
  id_token: string;
  access_token: string;
  refresh_token: string;
}

interface SignupRequest { email: string; password: string; display_name: string; }
interface SignupResponse { user_id: string; email: string; }
interface ConfirmRequest { email: string; confirmation_code: string; }
interface ConfirmResponse { confirmed: boolean; }
interface LoginRequest { email: string; password: string; }
interface LoginResponse { tokens: CognitoTokens; user: { user_id: string; name: string; email: string; role: ... }; }
interface ResendCodeRequest { email: string; }
interface ResendCodeResponse { sent: boolean; }
interface RegisterRequest { invite_code: string; device_name: string; platform: 'ios' | 'android'; display_name: string; }
interface RegisterResponse { user_id: string; device_token: string; }
```

### Streaming Types

```typescript
interface SSEEvent {
  type: 'text_delta' | 'message_done' | 'error';
  content?: string;
  conversation_id?: string;
  message_id?: string;
}

interface VoiceEvent {
  type: 'audio_chunk' | 'transcript' | 'session_end' | 'error';
  data?: string;
  role?: string;
  content?: string;
}
```

### API Response Wrappers

```typescript
interface ConversationListResponse { conversations: Conversation[]; next_cursor?: string; }
interface MessageListResponse { messages: Message[]; next_cursor?: string; }
interface ProfileListResponse { profiles: MemberProfile[]; }
interface AgentTypesResponse { agent_types: Record<string, AgentTypeInfo>; }
interface AgentConfigsResponse { agent_configs: AgentConfig[]; }
interface AgentTemplatesResponse { templates: AgentTemplate[]; }
interface AvailableAgentsResponse { agents: AvailableAgent[]; }
interface PermissionsResponse { permissions: PermissionGrant[]; }
interface RequiredPermissionsResponse { agent_type: string; required_permissions: PermissionType[]; }
interface FamilyRelationshipsResponse { relationships: FamilyRelationship[]; }

interface SessionBootstrapResponse {
  user: { user_id: string; name: string; email: string; role: 'admin' | 'member' | 'owner'; };
  profile: MemberProfile | null;
  family: { info: Family; members: FamilyMember[]; } | null;
  agents: { available: AvailableAgent[]; my_configs: AgentConfig[]; agent_types: Record<string, AgentTypeInfo>; };
  permissions: PermissionGrant[];
  conversations: { items: Conversation[]; next_cursor?: string; };
}
```

---

## 7. Key Patterns

### Optimistic UI Updates

- **Chat messages:** User messages appear instantly before the API responds. The assistant message placeholder is added before streaming begins.
- **Conversation creation:** When a new conversation is created (no prior `conversationId`), the `message_done` SSE event includes the new `conversation_id`. The screen calls `actions.addConversation()` to prepend it to the store immediately, avoiding a full refresh.
- **Permission toggles (MyAgentsScreen):** `localPermissionOverrides` provides immediate UI feedback while the actual API call is in flight. After `refreshPermissions()` completes, the overrides are cleared and the real data takes over.
- **Relationship changes (FamilyTreeScreen):** `relationshipMap` is updated locally immediately after the API call succeeds, without waiting for a full refresh.

### Error Handling

- All API calls use try/catch with `Alert.alert()` to display error messages.
- The `request()` helper in `api.ts` parses error bodies and throws `Error` with the server's `error` field or a status-based fallback.
- 401 errors trigger the global `authExpired` event bus, which logs the user out and resets navigation.
- Network errors during SSE streaming are caught by `xhr.onerror` and surfaced as assistant messages.

### Loading States

- **Global:** `session.status === 'loading'` shows a splash screen in `AppContent`.
- **Per-screen:** Most screens have a `loading` boolean that shows `ActivityIndicator` until initial data loads.
- **Per-action:** Buttons track individual `saving`, `deleting`, `toggling` states and disable themselves / show "Saving..." text.
- **Pull-to-refresh:** `ConversationListScreen` and `MyAgentsScreen` use `refreshing` with `FlatList`'s native pull-to-refresh.
- **Stale refresh:** `ConversationListScreen` uses a 30-second threshold (`REFRESH_THRESHOLD_MS`) to decide whether to refresh on focus.

### Agent Permission System UI

The agent system uses a **two-layer authorization model**:

1. **Admin layer (AdminMemberDetailScreen):** Admins toggle agent types per member. This creates/deletes `AgentConfig` records. The toggle iterates over all `agentTypes` from the session store.

2. **Member layer (MyAgentsScreen):** Members see only agents that the admin has authorized (filtered by `myConfigs`). They can enable/disable their authorized agents and manage required permissions.

Each agent template can declare `required_permissions` (e.g., `['email_access', 'calendar_access']`). The MyAgentsScreen:
- Shows a collapsed summary: "All permissions granted" or "N permissions needed"
- Shows a "Setup Required" badge on enabled agents with missing permissions
- Expands to a permissions panel on tap, with individual toggle switches
- Special-cases `email_access` to redirect to `AgentSetupScreen` instead of using a default config

Permission labels are mapped via a local `PERMISSION_LABELS` dictionary:
```typescript
const PERMISSION_LABELS: Record<string, string> = {
  email_access: 'Email Account Access',
  calendar_access: 'Calendar Access',
  health_data: 'Health Data Access',
  medical_records: 'Medical Records Access',
};
```
