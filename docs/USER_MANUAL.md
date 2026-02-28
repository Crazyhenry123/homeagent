# HomeAgent — User Manual

## What is HomeAgent?

HomeAgent is a family AI assistant app. Each family member has their own account and can chat with an AI assistant powered by Claude. Conversations are private — each person can only see their own chats.

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

### Deleting a Chat

1. From the conversation list, swipe left on a conversation (or long-press, depending on your device)
2. Confirm deletion

Deleted conversations cannot be recovered.

### Settings

Tap the gear icon to access settings:
- **Your Name** — The name you registered with
- **Logout** — Signs you out and clears your device token. You'll need a new invite code to register again.

---

## Tips

- **Be specific** — The more context you give the assistant, the better the response.
- **Conversations are private** — No one else can see your chats, not even the admin.
- **New conversations for new topics** — Start a new chat when switching subjects. This gives the assistant a clean context.
- **The assistant is streaming** — You'll see the response appear word by word. Wait for it to finish before sending your next message.

---

## For Family Admins

### What is an Admin?

The first person to register with the pre-configured invite code (default: `FAMILY`) becomes the admin. Admins can create invite codes for other family members.

### Creating Invite Codes

As an admin, you can generate invite codes for family members. Currently this is done via the API:

```bash
# Get your device token (saved during registration)
TOKEN="your-device-token-here"

# Create a new invite code
curl -X POST http://<BACKEND-URL>/api/admin/invite-codes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

Response:
```json
{
  "code": "AB12CD",
  "expires_at": "2099-12-31T00:00:00+00:00"
}
```

Share this 6-character code with the family member. Each code can only be used once.

### Managing the Backend

The backend URL is:
```
http://Deploy-Servi-XjO6myh4gADc-1702122244.us-east-1.elb.amazonaws.com
```

Useful commands:

```bash
# Check backend health
curl http://<BACKEND-URL>/health

# Register a new user manually
curl -X POST http://<BACKEND-URL>/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "invite_code": "AB12CD",
    "device_name": "Mom iPhone",
    "platform": "ios",
    "display_name": "Mom"
  }'
```

---

## Troubleshooting

### "Invite code already used or expired"

Each invite code can only be used once. Ask the admin to generate a new one.

### App shows "Network Error"

- Check that your phone has internet access
- The backend may be temporarily unavailable — try again in a few minutes
- If using the development build, ensure your phone and computer are on the same WiFi network

### Slow Responses

The AI assistant is a large language model that generates responses in real-time. Response speed depends on:
- Message complexity and length
- Current server load
- Network conditions

Typical response time: 2–10 seconds for the first tokens to appear.

### Lost Access

If you log out or lose your device, you'll need a new invite code from the admin to register again. Your previous conversations are not recoverable from a new device.

---

## Privacy & Data

- All conversations are stored in Amazon DynamoDB (encrypted at rest)
- Conversations are private to each user
- Messages are sent to Amazon Bedrock (Claude) for AI responses
- No data is shared with third parties
- The admin cannot read other users' conversations
- Deleting a conversation permanently removes all its messages
