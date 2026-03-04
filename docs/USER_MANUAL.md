# HomeAgent — User Manual

## What is HomeAgent?

HomeAgent is a family AI assistant app. Each family member has their own account and can chat with an AI assistant powered by Claude. You can send text messages, attach images for the assistant to analyze, and use voice mode for hands-free conversation. Conversations are private — each person can only see their own chats. The assistant can be extended with specialized agents (health advisor, meal planner, etc.) that members can enable for themselves.

---

## Getting Started

### 1. Install Expo Go

Download **Expo Go** from the App Store (iOS) or Google Play Store (Android). It's free.

### 2. Open the App

You'll receive a link or QR code from your family admin. Scan the QR code with:
- **iOS:** Open the Camera app and point at the QR code
- **Android:** Open Expo Go and tap "Scan QR Code"

### 3. Register

You'll need an **invite code** from your family admin (a 6-character code like `AB12CD`).

1. Enter the invite code
2. Enter your name (this is how the app will greet you)
3. Tap **Register**

Your account is now created. You won't need to register again — the app remembers you.

---

## Using the App

### Starting a New Chat

1. From the conversation list, tap the **+** button
2. Type your message and tap **Send**
3. The AI assistant will respond in real-time — you'll see the text appear as it's being generated

### Continuing a Chat

1. From the conversation list, tap any existing conversation
2. Your previous messages are loaded
3. Type a new message to continue the conversation

The assistant remembers the context of your conversation (up to the last 50 messages).

### Sending Images

You can attach images for the assistant to see and analyze (e.g., a photo of a meal, a document, a rash).

1. In a chat, tap the **+** button next to the text input
2. Select one or more images from your photo library (up to 5 per message)
3. Selected images appear as thumbnails above the input field
4. Tap the **X** on any thumbnail to remove it
5. Type an optional message and tap **Send**

The assistant will describe and respond to the image content. You can send images with or without accompanying text.

**Limits:** Up to 5 images per message, each up to 5 MB. Supported formats: JPEG, PNG, GIF, WebP.

### Using Voice Mode

Voice mode lets you have a spoken conversation with the assistant.

1. In a chat, tap the **microphone** button (right of the Send button)
2. Wait for the connection (status changes from "Connecting..." to "Tap to speak")
3. Tap the blue **MIC** button to start recording
4. Speak your question, then tap **STOP**
5. The assistant will respond with audio — you'll hear the reply through your speaker
6. Transcripts of both your speech and the assistant's response appear on screen
7. Tap **Back to Chat** to return to the text chat

When you provide a conversation ID, voice transcripts are saved to that conversation's history so you can refer back to them later.

### Deleting a Chat

1. From the conversation list, long-press on a conversation
2. Confirm deletion

Deleted conversations cannot be recovered.

---

## My Profile

Tap **Settings** > **Edit My Profile** to update your information:

- **Display Name** — How the assistant addresses you
- **Family Role** — Your role in the family (parent, child, grandparent, etc.)
- **Health Notes** — Any health information relevant to you
- **Interests** — Topics you're interested in

Your profile helps the assistant give personalized advice.

---

## My Agents

Agents are specialized AI assistants that extend your personal assistant's capabilities. Go to **Settings** > **My Agents** to browse and enable agents.

### How Agents Work

1. Your family admin creates and configures agent templates
2. Available agents appear in **My Agents** with a description of what they do
3. Toggle an agent **on** to enable it — the assistant will now use it when relevant
4. Toggle it **off** to disable it

### Built-in Agents

- **Health Advisor** — Comprehensive health guidance with access to your family's health records, observations, and conversation history

### Custom Agents

Your admin may create additional agents (e.g., Meal Planner, Homework Helper) that appear in your **My Agents** list.

---

## Settings

Tap the gear icon to access settings:

- **Account** — Your name, user ID, and role
- **Edit My Profile** — Update your profile information
- **My Agents** — Browse and toggle available AI agents
- **Log Out** — Signs you out (you'll need a new invite code to register again)

---

## Tips

- **Be specific** — The more context you give the assistant, the better the response.
- **Use images** — Attach a photo when words aren't enough (e.g., "What plant is this?").
- **Try voice mode** — Use the mic button for hands-free conversation while cooking, exercising, etc.
- **Conversations are private** — No one else can see your chats, not even the admin.
- **New conversations for new topics** — Start a new chat when switching subjects.
- **Enable relevant agents** — Turn on agents in My Agents to get specialized help.
- **The assistant is streaming** — You'll see the response appear word by word. Wait for it to finish before sending your next message.

---

## For Family Admins

### What is an Admin?

The first person to register with the pre-configured invite code (default: `FAMILY`) becomes the admin. Admins have additional capabilities.

### Admin Capabilities

From **Settings**, admins see additional options:

#### Manage Family Members
View all family members, edit their profiles, configure agents for them, or remove members.

#### Manage Family Tree
Define relationships between family members (parent/child, spouse, sibling). This helps the health advisor understand family context.

#### Manage Agent Templates
Create, edit, and delete custom AI agent types:

1. Tap **Manage Agent Templates**
2. Tap **Add New Agent** to create a new agent type
3. Fill in:
   - **Name** — Display name (e.g., "Meal Planner")
   - **Agent Type** — Unique slug (e.g., `meal_planner`)
   - **Description** — What the agent does
   - **System Prompt** — Instructions that define the agent's behavior
   - **Availability** — Toggle whether all members can see it, or restrict to specific members
4. Built-in agents (Health Advisor, etc.) can be edited but not deleted

#### Generate Invite Code
Create single-use invite codes to give to family members for registration.

---

## Troubleshooting

### "Invite code already used or expired"
Each invite code can only be used once. Ask the admin to generate a new one.

### App shows "Network Error"
- Check that your phone has internet access
- The backend may be temporarily unavailable — try again in a few minutes
- If using the development build, ensure your phone and computer are on the same WiFi network

### Slow Responses
The AI assistant generates responses in real-time. Response speed depends on:
- Message complexity and length
- Current server load
- Network conditions

Typical response time: 2–10 seconds for the first tokens to appear.

### "No Agents Available"
Your admin hasn't made any agents available to you yet. Ask them to check agent template availability settings.

### Lost Access
If you log out or lose your device, you'll need a new invite code from the admin to register again. Your previous conversations are not recoverable from a new device.

---

## Privacy & Data

- All conversations are stored in Amazon DynamoDB (encrypted at rest)
- Conversations are private to each user
- Messages are sent to Amazon Bedrock (Claude) for AI responses
- Images you attach are uploaded to Amazon S3 (encrypted) and sent to Claude for analysis
- Voice audio is streamed to Amazon Nova Sonic for speech-to-text and text-to-speech
- Health documents are stored in Amazon S3 (encrypted)
- No data is shared with third parties
- The admin cannot read other users' conversations
- Deleting a conversation permanently removes all its messages
