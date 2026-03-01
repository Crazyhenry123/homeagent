# HomeAgent iOS Test Guide

## Prerequisites

1. **iPhone** running iOS 16+
2. **Expo Go** app installed from the App Store
3. **Expo dev server** running on the host machine:
   ```bash
   cd mobile && npx expo start --tunnel
   ```
4. **Backend** running (either local via `docker compose up` or the deployed ECS instance)

## How to Connect

Open your iPhone camera and scan the QR code shown in the Expo terminal, or manually open this URL in Safari:

```
exp://6dkxhze-anonymous-8081.exp.direct
```

The app will load inside Expo Go.

> **API endpoint**: The app is configured to hit the deployed backend at
> `http://Deploy-Servi-XjO6myh4gADc-1702122244.us-east-1.elb.amazonaws.com`.
> No manual configuration is needed.

---

## Test Cases

### 1. Registration Flow

**Screen**: Register (first screen when no token stored)

| # | Step | Expected Result |
|---|------|-----------------|
| 1.1 | App opens for the first time | "Welcome to HomeAgent" screen with Invite Code and Your Name fields |
| 1.2 | Tap "Join Family" with empty fields | Alert: "Please fill in all fields" |
| 1.3 | Enter an invalid invite code (e.g. `WRONG`) and a name, tap "Join Family" | Alert: "Registration Failed" with error message from server |
| 1.4 | Enter `FAMILY` as invite code, enter your name, tap "Join Family" | Button shows "Registering...", then navigates to Conversation List |
| 1.5 | Kill and reopen the app | App goes directly to Conversation List (token persisted in secure storage) |

---

### 2. Conversation List Screen

**Screen**: Chats (main screen after login)

| # | Step | Expected Result |
|---|------|-----------------|
| 2.1 | View empty conversation list | "No conversations yet" message with "Tap + to start chatting" subtitle |
| 2.2 | Pull down on the list | Refresh spinner appears, list reloads |
| 2.3 | Tap the blue **+** FAB button (bottom right) | Navigates to Chat screen with "New Chat" title in header |
| 2.4 | After creating conversations (see section 3), come back to this screen | Conversations listed with titles and relative timestamps (e.g. "2m ago") |
| 2.5 | Tap a conversation | Navigates to Chat screen with conversation title in header, existing messages load |
| 2.6 | Navigate away and come back | Conversation list refreshes automatically on screen focus |

---

### 3. Chat & Streaming

**Screen**: Chat (New Chat or existing conversation)

| # | Step | Expected Result |
|---|------|-----------------|
| 3.1 | Type a message and tap Send | User message bubble appears on the right (blue) |
| 3.2 | Watch the response | Assistant message bubble appears on the left (gray), text streams in word-by-word via SSE |
| 3.3 | While streaming, observe the input area | Send button is disabled during streaming, re-enables when done |
| 3.4 | After the response completes | If this was a new chat, the header title updates to reflect the conversation topic |
| 3.5 | Send multiple messages in the same conversation | Messages accumulate, screen auto-scrolls to the latest message |
| 3.6 | Tap the back arrow to return to Conversation List | New conversation now appears in the list with a title and timestamp |

**Keyboard behavior (iOS-specific)**:

| # | Step | Expected Result |
|---|------|-----------------|
| 3.7 | Tap the message input field | Keyboard slides up, input area stays visible above the keyboard (not hidden behind it) |
| 3.8 | Type a long message that wraps | Input area grows vertically to fit the text |
| 3.9 | Dismiss keyboard (tap outside or swipe down) | Input area returns to normal position |

---

### 4. Loading States

| # | Step | Expected Result |
|---|------|-----------------|
| 4.1 | Tap an existing conversation | Loading spinner appears while messages are fetched, then messages render |
| 4.2 | Open Settings screen | Loading spinner appears briefly while user info is verified with the server |

---

### 5. Delete Conversation

**Screen**: Conversation List

| # | Step | Expected Result |
|---|------|-----------------|
| 5.1 | Long-press on a conversation item | Alert appears: "Delete Conversation" / "Are you sure?" with Cancel and Delete buttons |
| 5.2 | Tap **Cancel** | Alert dismisses, conversation is still there |
| 5.3 | Long-press again and tap **Delete** | Conversation removed from the list immediately |
| 5.4 | Pull to refresh | Deleted conversation does not reappear (server-side deletion confirmed) |

---

### 6. Settings Screen

**Screen**: Settings (tap "Settings" in the header of Conversation List)

| # | Step | Expected Result |
|---|------|-----------------|
| 6.1 | Tap "Settings" in the Chats header | Navigates to Settings screen with loading spinner |
| 6.2 | After loading | Displays ACCOUNT section with Name, User ID, and Role fields |
| 6.3 | Verify Name | Shows the display name you entered during registration |
| 6.4 | Verify Role | Shows "admin" (since you registered with the `FAMILY` admin invite code) |
| 6.5 | Verify version | "HomeAgent v0.1.0" shown at the bottom |

---

### 7. Admin: Generate Invite Code

**Screen**: Settings (only visible for admin users)

| # | Step | Expected Result |
|---|------|-----------------|
| 7.1 | Verify ADMIN section is visible | "ADMIN" section header with "Generate Invite Code" button appears below the account info |
| 7.2 | Tap "Generate Invite Code" | Button text changes to "Generating...", then alert shows: "Invite Code Created" with a 6-character code |
| 7.3 | Note the generated code | You'll use this to test multi-user registration (step 8) |
| 7.4 | Tap "OK" | Alert dismisses |

---

### 8. Multi-User Registration (with generated invite code)

| # | Step | Expected Result |
|---|------|-----------------|
| 8.1 | Log out (see section 9) | Returns to Register screen |
| 8.2 | Enter the invite code from step 7.3 and a different name | Registration succeeds, navigates to Conversation List |
| 8.3 | Go to Settings | Role shows "member" (not admin) |
| 8.4 | Verify ADMIN section is NOT visible | Only ACCOUNT section, Log Out button, and version are shown |
| 8.5 | Try the same invite code again (log out and re-register) | Registration fails — invite codes are single-use |

---

### 9. Log Out

**Screen**: Settings

| # | Step | Expected Result |
|---|------|-----------------|
| 9.1 | Tap the red "Log Out" button | Alert: "Log Out" / "You will need an invite code to log back in." with Cancel and Log Out |
| 9.2 | Tap **Cancel** | Alert dismisses, stays on Settings |
| 9.3 | Tap **Log Out** | Token cleared, navigates to Register screen |
| 9.4 | Kill and reopen the app | Opens to Register screen (token was cleared) |

---

### 10. Auth Expiry (401 Handling)

This tests the automatic session expiry detection.

| # | Step | Expected Result |
|---|------|-----------------|
| 10.1 | Register and start using the app normally | App works, conversations load |
| 10.2 | Simulate token expiry: stop the backend, clear the Devices DynamoDB table, restart backend | Next API call from the app will return 401 |
| 10.3 | Trigger an API call (e.g. pull to refresh conversation list) | Alert: "Session Expired" / "Please register again with an invite code." |
| 10.4 | Tap OK | Navigates to Register screen |
| 10.5 | Verify no duplicate alerts | Only one "Session Expired" alert should appear, even if multiple requests fail at the same time (debounce guard) |

---

### 11. Error Handling

| # | Step | Expected Result |
|---|------|-----------------|
| 11.1 | Stop the backend (`docker compose down`), then try to send a message | Error message appears in the chat bubble (red text) |
| 11.2 | Stop backend, pull to refresh conversation list | Alert: "Error" / "Failed to load conversations" |
| 11.3 | Stop backend, try to register | Alert: "Registration Failed" with connection error message |

---

### 12. Navigation Edge Cases

| # | Step | Expected Result |
|---|------|-----------------|
| 12.1 | Rapidly tap the + button multiple times | Only one Chat screen opens (no double-navigation) |
| 12.2 | Tap back while a response is streaming | Navigates back to Conversation List; stream is aborted (no crash) |
| 12.3 | Open Settings, go back, open a chat, go back | Navigation stack works correctly with no stale state |

---

## Quick Smoke Test (5 minutes)

If you're short on time, run through these steps for a quick confidence check:

1. Open app -> Register with code `FAMILY` and your name
2. Tap **+** -> Send "Hello, what can you help me with?" -> Verify streaming response
3. Tap back -> Verify conversation appears in list with a title
4. Long-press conversation -> Delete -> Verify it disappears
5. Tap Settings -> Verify name/role/admin section -> Generate an invite code
6. Log Out -> Verify you're back at Register screen
