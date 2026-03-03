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

Open your iPhone camera and scan the QR code shown in the Expo terminal. The app will load inside Expo Go.

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
| 3.7 | Tap the message input field | Keyboard slides up, input area stays visible above the keyboard |
| 3.8 | Type a long message that wraps | Input area grows vertically to fit the text |
| 3.9 | Dismiss keyboard (tap outside or swipe down) | Input area returns to normal position |

---

### 4. Delete Conversation

**Screen**: Conversation List

| # | Step | Expected Result |
|---|------|-----------------|
| 4.1 | Long-press on a conversation item | Alert appears: "Delete Conversation" with Cancel and Delete buttons |
| 4.2 | Tap **Cancel** | Alert dismisses, conversation is still there |
| 4.3 | Long-press again and tap **Delete** | Conversation removed from the list immediately |
| 4.4 | Pull to refresh | Deleted conversation does not reappear |

---

### 5. Profile Screen

**Screen**: Settings > Edit My Profile

| # | Step | Expected Result |
|---|------|-----------------|
| 5.1 | Tap "Edit My Profile" in Settings | Navigates to Profile screen with editable fields |
| 5.2 | Edit display name and save | Profile updates successfully |
| 5.3 | Edit family role, health notes, interests | All fields persist after save |

---

### 6. Settings Screen

**Screen**: Settings (tap "Settings" in the Chats header)

| # | Step | Expected Result |
|---|------|-----------------|
| 6.1 | Tap "Settings" in the Chats header | Navigates to Settings screen |
| 6.2 | After loading | Displays ACCOUNT section with Name, User ID, and Role fields |
| 6.3 | Verify PROFILE section | "Edit My Profile" and "My Agents" buttons visible |
| 6.4 | (Admin only) Verify ADMIN section | "Manage Family Members", "Manage Family Tree", "Manage Agent Templates", "Generate Invite Code" visible |
| 6.5 | Verify version | "HomeAgent v0.1.0" shown at the bottom |

---

### 7. My Agents Screen (Member Self-Service)

**Screen**: Settings > My Agents

| # | Step | Expected Result |
|---|------|-----------------|
| 7.1 | Tap "My Agents" | Navigates to My Agents screen |
| 7.2 | View list of available agents | Health Advisor, Logistics Assistant, Shopping Assistant shown with descriptions and toggle switches |
| 7.3 | Toggle Health Advisor ON | Switch turns green, agent is now enabled |
| 7.4 | Toggle Health Advisor OFF | Switch turns gray, agent is now disabled |
| 7.5 | Start a chat and ask a health question (with Health Advisor enabled) | The assistant uses the Health Advisor sub-agent to provide detailed health guidance |

---

### 8. Admin: Manage Agent Templates

**Screen**: Settings > Manage Agent Templates (admin only)

| # | Step | Expected Result |
|---|------|-----------------|
| 8.1 | Tap "Manage Agent Templates" | Navigates to Agent Templates screen |
| 8.2 | View template list | Built-in agents shown with "Built-in" badge |
| 8.3 | Tap "Add New Agent" | Modal form opens with Name, Agent Type, Description, System Prompt, Availability fields |
| 8.4 | Fill in all fields and tap Save | New template appears in the list |
| 8.5 | Tap an existing template | Edit modal opens with fields pre-filled |
| 8.6 | Edit name/description and save | Template updates |
| 8.7 | Try to delete a built-in template | Error alert: "Cannot delete built-in agent templates" |
| 8.8 | Delete a custom template | Template removed from list after confirmation |

---

### 9. Admin: Family Members

**Screen**: Settings > Manage Family Members (admin only)

| # | Step | Expected Result |
|---|------|-----------------|
| 9.1 | Tap "Manage Family Members" | Navigates to members list with all registered users |
| 9.2 | Tap a member | Navigates to member detail with profile info and agent configuration |
| 9.3 | Toggle agents for the member | Agent config saved |

---

### 10. Admin: Family Tree

**Screen**: Settings > Manage Family Tree (admin only)

| # | Step | Expected Result |
|---|------|-----------------|
| 10.1 | Tap "Manage Family Tree" | Navigates to Family Tree screen |
| 10.2 | Add a relationship between two members | Relationship created (bidirectional) |
| 10.3 | Delete a relationship | Relationship removed |

---

### 11. Admin: Generate Invite Code

**Screen**: Settings (admin only)

| # | Step | Expected Result |
|---|------|-----------------|
| 11.1 | Tap "Generate Invite Code" | Button text changes to "Generating...", then alert shows: "Invite Code Created" with a 6-character code |
| 11.2 | Note the generated code | Use this for multi-user registration |

---

### 12. Multi-User Registration

| # | Step | Expected Result |
|---|------|-----------------|
| 12.1 | Log out (see section 14) | Returns to Register screen |
| 12.2 | Enter the generated invite code and a different name | Registration succeeds |
| 12.3 | Go to Settings | Role shows "member" (not admin) |
| 12.4 | Verify ADMIN section is NOT visible | Only ACCOUNT, PROFILE sections visible |
| 12.5 | Go to My Agents | Available agents listed with toggles |
| 12.6 | Try the same invite code again (log out and re-register) | Registration fails — invite codes are single-use |

---

### 13. Error Handling

| # | Step | Expected Result |
|---|------|-----------------|
| 13.1 | Stop the backend, then try to send a message | Error message appears |
| 13.2 | Stop backend, pull to refresh conversation list | Error alert |
| 13.3 | Stop backend, try to register | Alert: "Registration Failed" with connection error |

---

### 14. Log Out

**Screen**: Settings

| # | Step | Expected Result |
|---|------|-----------------|
| 14.1 | Tap the red "Log Out" button | Alert: "Log Out" / "You will need an invite code to log back in." |
| 14.2 | Tap **Cancel** | Alert dismisses, stays on Settings |
| 14.3 | Tap **Log Out** | Token cleared, navigates to Register screen |
| 14.4 | Kill and reopen the app | Opens to Register screen (token was cleared) |

---

### 15. Auth Expiry (401 Handling)

| # | Step | Expected Result |
|---|------|-----------------|
| 15.1 | Register and start using the app normally | App works |
| 15.2 | Simulate token expiry: stop backend, clear Devices table, restart backend | Next API call returns 401 |
| 15.3 | Trigger an API call (e.g. pull to refresh) | Alert: "Session Expired" |
| 15.4 | Tap OK | Navigates to Register screen |

---

## Quick Smoke Test (5 minutes)

1. Open app -> Register with code `FAMILY` and your name
2. Tap **+** -> Send "Hello, what can you help me with?" -> Verify streaming response
3. Tap back -> Verify conversation appears in list
4. Go to Settings -> My Agents -> Toggle Health Advisor ON
5. New chat -> Ask a health question -> Verify the health advisor sub-agent is used
6. Settings -> Manage Agent Templates -> Verify built-in templates listed
7. Long-press conversation -> Delete -> Verify it disappears
8. Generate an invite code -> Log Out -> Verify Register screen
