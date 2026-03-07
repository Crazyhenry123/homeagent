Now I have a complete picture of the entire codebase. Let me produce the implementation plan.

---

# HomeAgent Mobile UI Redesign -- Concrete Implementation Plan

---

## 1. Dependency Check

### Currently Installed
| Package | Version | Status |
|---------|---------|--------|
| `expo` | `^54.0.0` | Installed |
| `@react-navigation/native` | `^7.0.0` | Installed |
| `@react-navigation/native-stack` | `^7.0.0` | Installed |
| `react-native-safe-area-context` | `~5.6.0` | Installed |
| `react-native-screens` | `~4.16.0` | Installed |
| `expo-av` | `~16.0.8` | Installed |
| `expo-image-picker` | `~17.0.10` | Installed |
| `expo-file-system` | `~19.0.21` | Installed |
| `expo-secure-store` | `~15.0.8` | Installed |
| `expo-splash-screen` | `~31.0.13` | Installed |
| `expo-status-bar` | `~3.0.9` | Installed |
| `expo-constants` | `~18.0.13` | Installed |
| `expo-font` | `~14.0.11` | Installed |
| `expo-asset` | `~12.0.12` | Installed |

### Must Install (all confirmed NOT installed)

Run this single command from `/home/ubuntu/homeagent/mobile`:

```bash
npx expo install @expo/vector-icons expo-haptics react-native-reanimated expo-linear-gradient expo-blur @react-navigation/bottom-tabs react-native-markdown-display @react-native-segmented-control/segmented-control
```

| Package | Purpose | Phase |
|---------|---------|-------|
| `@expo/vector-icons` | Ionicons, MaterialIcons, FontAwesome throughout the app | Phase 1 |
| `expo-haptics` | Haptic feedback on buttons, toggles, send, delete | Phase 1 |
| `react-native-reanimated` | Typing indicator animation, recording pulse, transitions | Phase 1 (foundation), Phase 3 (chat animations) |
| `expo-linear-gradient` | RegisterScreen branded header, splash screen | Phase 1 |
| `expo-blur` | VoiceMode overlay blur, modal backdrops | Phase 3 |
| `@react-navigation/bottom-tabs` | Tab navigator for Chats/Family/Agents/Settings | Phase 2 |
| `react-native-markdown-display` | Render markdown in assistant messages | Phase 3 |
| `@react-native-segmented-control/segmented-control` | Sharing level selector on SettingsScreen | Phase 1 |

### babel.config.js Update Required

After installing `react-native-reanimated`, update `/home/ubuntu/homeagent/mobile/babel.config.js`:

```js
module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: ['react-native-reanimated/plugin'],
  };
};
```

The `reanimated/plugin` **must** be the last item in the `plugins` array. This is a hard requirement.

---

## 2. New Files to Create

### Theme System (Phase 1)

**File: `/home/ubuntu/homeagent/mobile/src/theme/colors.ts`**
```ts
export const colors = {
  // Primary
  primary: '#007AFF',
  primaryLight: '#EBF5FF',

  // Backgrounds
  background: '#F2F2F7',
  surface: '#FFFFFF',
  surfaceSecondary: '#F9F9F9',

  // Text
  textPrimary: '#1C1C1E',
  textSecondary: '#8E8E93',
  textTertiary: '#AEAEB2',

  // Separators
  separator: '#E5E5EA',
  separatorOpaque: '#C6C6C8',

  // Chat
  userBubble: '#007AFF',
  assistantBubble: '#F0F0F5',
  userBubbleText: '#FFFFFF',
  assistantBubbleText: '#1C1C1E',

  // Semantic
  destructive: '#FF3B30',
  success: '#34C759',
  warning: '#FF9500',

  // UI Elements
  disabledBackground: '#B0B0B0',
  disabledText: '#B0B0B0',
  chevron: '#C7C7CC',
  badgeBackground: '#E5E5EA',
  setupBadgeBackground: '#FFE0B2',
  setupBadgeText: '#E65100',

  // Voice Mode (dark theme)
  voiceBackground: '#1C1C1E',
  voiceSurface: '#2C2C2E',
  voiceSurfaceSecondary: '#3A3A3C',
  voiceError: '#FF453A',
  voiceDisabled: '#48484A',
} as const;

export type ColorToken = keyof typeof colors;
```

**File: `/home/ubuntu/homeagent/mobile/src/theme/typography.ts`**
```ts
import {TextStyle} from 'react-native';

export const typography = {
  largeTitle: {fontSize: 34, fontWeight: '700', lineHeight: 41} as TextStyle,
  title1: {fontSize: 28, fontWeight: '700', lineHeight: 34} as TextStyle,
  title2: {fontSize: 22, fontWeight: '600', lineHeight: 28} as TextStyle,
  title3: {fontSize: 20, fontWeight: '600', lineHeight: 25} as TextStyle,
  headline: {fontSize: 17, fontWeight: '600', lineHeight: 22} as TextStyle,
  body: {fontSize: 16, fontWeight: '400', lineHeight: 22} as TextStyle,
  callout: {fontSize: 15, fontWeight: '400', lineHeight: 20} as TextStyle,
  subheadline: {fontSize: 14, fontWeight: '400', lineHeight: 18} as TextStyle,
  footnote: {fontSize: 13, fontWeight: '500', lineHeight: 18, letterSpacing: 0.5} as TextStyle,
  caption1: {fontSize: 12, fontWeight: '400', lineHeight: 16} as TextStyle,
  caption2: {fontSize: 11, fontWeight: '400', lineHeight: 13} as TextStyle,
} as const;

export type TypographyToken = keyof typeof typography;
```

**File: `/home/ubuntu/homeagent/mobile/src/theme/spacing.ts`**
```ts
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const;

export type SpacingToken = keyof typeof spacing;
```

**File: `/home/ubuntu/homeagent/mobile/src/theme/index.ts`**
```ts
export {colors} from './colors';
export {typography} from './typography';
export {spacing} from './spacing';
```

### Reusable Components (Phase 1)

**File: `/home/ubuntu/homeagent/mobile/src/components/ui/SectionHeader.tsx`**
```ts
// Props interface:
interface SectionHeaderProps {
  title: string;
  rightElement?: React.ReactNode;  // e.g. ActivityIndicator, badge
}
// Renders the standard section header pattern used in 8+ screens.
// Uses theme.typography.footnote + theme.colors.textSecondary.
// Replaces: sectionHeader + sectionHeaderText styles in Settings, Profile,
//   AdminPanel, AdminMemberDetail, FamilyTree, FamilyManage, AdminAgentTemplates, ConversationListScreen.
```

**File: `/home/ubuntu/homeagent/mobile/src/components/ui/SettingsRow.tsx`**
```ts
// Props interface:
interface SettingsRowProps {
  icon?: string;          // Ionicons name
  iconColor?: string;     // defaults to colors.primary
  label: string;
  sublabel?: string;
  value?: string;         // right-side text
  showChevron?: boolean;  // defaults to true
  onPress?: () => void;
  destructive?: boolean;  // red text
}
// Renders white bg row with icon, label, optional sublabel, optional right value,
// optional chevron. Touch feedback with haptic.
// Replaces: actionRow/toggleRow patterns in Settings, AdminPanel, AdminMembers.
```

**File: `/home/ubuntu/homeagent/mobile/src/components/ui/ToggleRow.tsx`**
```ts
// Props interface:
interface ToggleRowProps {
  label: string;
  sublabel?: string;
  value: boolean;
  onValueChange: (value: boolean) => void;
  disabled?: boolean;
}
// Renders white bg row with label and Switch, with haptic on toggle.
// Replaces: toggleRow pattern in Settings, AdminMemberDetail, AgentSetup.
```

**File: `/home/ubuntu/homeagent/mobile/src/components/ui/PrimaryButton.tsx`**
```ts
// Props interface:
interface PrimaryButtonProps {
  title: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  variant?: 'primary' | 'secondary' | 'destructive';
  icon?: string;  // Ionicons name, shown left of text
}
// Renders the standard 48h / borderRadius 10 / blue bg button.
// primary = blue bg white text, secondary = white bg blue border, destructive = red bg.
// Adds haptic on press. Shows ActivityIndicator when loading.
// Replaces: saveButton, createButton, logoutButton, deleteButton, continueButton,
//   adminPanelButton patterns across all screens.
```

**File: `/home/ubuntu/homeagent/mobile/src/components/ui/Avatar.tsx`**
```ts
// Props interface:
interface AvatarProps {
  name: string;
  size?: number;  // defaults to 40
  color?: string; // auto-derived from name hash if not provided
}
// Renders a circle with first letter of name, colored background.
// Used in ConversationItem, AdminMembers member rows, FamilyManage, Settings header.
```

**File: `/home/ubuntu/homeagent/mobile/src/components/ui/EmptyState.tsx`**
```ts
// Props interface:
interface EmptyStateProps {
  icon?: string;         // Ionicons name
  title: string;
  subtitle?: string;
  actionLabel?: string;
  onAction?: () => void;
}
// Renders centered empty state with icon, title, subtitle, and optional action button.
// Replaces: empty/emptyText patterns in ConversationList, AdminMembers, MyAgents, FamilyManage.
```

**File: `/home/ubuntu/homeagent/mobile/src/components/ui/index.ts`**
```ts
export {SectionHeader} from './SectionHeader';
export {SettingsRow} from './SettingsRow';
export {ToggleRow} from './ToggleRow';
export {PrimaryButton} from './PrimaryButton';
export {Avatar} from './Avatar';
export {EmptyState} from './EmptyState';
```

### Chat Components (Phase 3)

**File: `/home/ubuntu/homeagent/mobile/src/components/TypingIndicator.tsx`**
```ts
// Props: none
// Renders three animated dots in an assistant bubble shape.
// Uses react-native-reanimated: three Animated.View circles that
// scale/opacity loop with staggered 200ms delay (0, 200ms, 400ms).
// Each dot: 8x8 circle, bg #8E8E93, animating between opacity 0.3 and 1.0.
// Wrapped in assistantBubble-styled container.
```

**File: `/home/ubuntu/homeagent/mobile/src/components/DaySeparator.tsx`**
```ts
// Props interface:
interface DaySeparatorProps {
  date: string;  // ISO string
}
// Renders centered text: "Today", "Yesterday", or formatted date.
// Light gray text, centered, with horizontal lines on each side.
```

**File: `/home/ubuntu/homeagent/mobile/src/components/ScrollToBottomButton.tsx`**
```ts
// Props interface:
interface ScrollToBottomButtonProps {
  visible: boolean;
  onPress: () => void;
}
// Floating circular button (36x36), positioned bottom-right above ChatInput.
// Ionicons "chevron-down" icon. Uses Reanimated FadeIn/FadeOut.
// Shadow matching the FAB style from ConversationList.
```

### Navigation (Phase 2)

**File: `/home/ubuntu/homeagent/mobile/src/navigation/MainTabNavigator.tsx`**
New file -- the bottom tab navigator.

**File: `/home/ubuntu/homeagent/mobile/src/navigation/ChatStack.tsx`**
New file -- native stack for Chats tab.

**File: `/home/ubuntu/homeagent/mobile/src/navigation/FamilyStack.tsx`**
New file -- native stack for Family tab.

**File: `/home/ubuntu/homeagent/mobile/src/navigation/AgentsStack.tsx`**
New file -- native stack for Agents tab.

**File: `/home/ubuntu/homeagent/mobile/src/navigation/SettingsStack.tsx`**
New file -- native stack for Settings tab.

**File: `/home/ubuntu/homeagent/mobile/src/navigation/AuthStack.tsx`**
New file -- native stack for unauthenticated screens.

**File: `/home/ubuntu/homeagent/mobile/src/navigation/types.ts`**
New file -- all param list types for every stack and tab navigator.

---

## 3. File-by-File Change Plan (All Phases)

### Legend
- `[P1]` = Phase 1 (Foundation + Quick Wins)
- `[P2]` = Phase 2 (Navigation Overhaul)
- `[P3]` = Phase 3 (Chat Experience)
- `DEP:` = depends on another change

---

### `/home/ubuntu/homeagent/mobile/package.json`
**[P1]** Add new dependencies via `npx expo install`. No manual edits needed.

### `/home/ubuntu/homeagent/mobile/babel.config.js`
**[P1]** Add `plugins: ['react-native-reanimated/plugin']` after the `presets` line. **DEP:** install react-native-reanimated first.

### `/home/ubuntu/homeagent/mobile/App.tsx`
**[P2]** No changes in P1. In P2, StatusBar style may change to `auto` for VoiceMode dark theme.

### `/home/ubuntu/homeagent/mobile/src/navigation/AppNavigator.tsx`
**[P1]** Replace hardcoded `#007AFF` on splash line 71 with `colors.primary`. Replace `#333` on line 162 with `colors.textPrimary`.

**[P2]** Major rewrite. This file becomes the top-level navigator that conditionally renders `AuthStack` or `MainTabNavigator` based on `session.status`. The current 13-screen flat Stack.Navigator is removed entirely. The `RootStackParamList` type export moves to `navigation/types.ts`.

Specific P2 changes:
- Remove all 13 `Stack.Screen` elements (lines 82-147)
- Import `AuthStack` and `MainTabNavigator`
- Conditionally render: `session.status === 'authenticated' ? <MainTabNavigator /> : <AuthStack />`
- Keep the splash screen logic (lines 67-74) but improve it with gradient
- Keep the auth expiration listener but update the reset logic to work with the new nav structure
- The `RootStackParamList` export is removed; each stack gets its own param list in `types.ts`

### `/home/ubuntu/homeagent/mobile/src/navigation/types.ts` (NEW)
**[P2]** Define:
```ts
// Auth screens
export type AuthStackParamList = {
  Register: undefined;
  AgentSetup: undefined;
};

// Chats tab
export type ChatStackParamList = {
  ConversationList: undefined;
  Chat: {conversationId?: string; title?: string};
  VoiceMode: {conversationId?: string};
};

// Family tab
export type FamilyStackParamList = {
  FamilyHome: undefined;       // merged AdminMembers + FamilyManage
  FamilyTree: undefined;
  AdminMemberDetail: {userId: string};
  FamilyManage: undefined;
};

// Agents tab
export type AgentsStackParamList = {
  MyAgents: undefined;
  AgentSetup: undefined;
  AdminAgentTemplates: undefined;
};

// Settings tab
export type SettingsStackParamList = {
  SettingsHome: undefined;
  Profile: undefined;
  AdminPanel: undefined;
};

// Tab navigator
export type MainTabParamList = {
  ChatsTab: undefined;
  FamilyTab: undefined;
  AgentsTab: undefined;
  SettingsTab: undefined;
};
```

### `/home/ubuntu/homeagent/mobile/src/navigation/MainTabNavigator.tsx` (NEW)
**[P2]** Creates bottom tab navigator with 4 tabs:
```ts
const Tab = createBottomTabNavigator<MainTabParamList>();

// Tab config:
// ChatsTab:    icon = "chatbubbles-outline" / "chatbubbles"
// FamilyTab:   icon = "people-outline" / "people"
// AgentsTab:   icon = "sparkles-outline" / "sparkles"
// SettingsTab: icon = "settings-outline" / "settings"
//
// Tab bar style: backgroundColor: colors.surface, borderTopColor: colors.separator
// Active tint: colors.primary, inactive: colors.textSecondary
// Label style: typography.caption2
```
FamilyTab visibility: conditional on `isOwnerOrAdmin` from useSession. If not admin, show only 3 tabs.

### `/home/ubuntu/homeagent/mobile/src/navigation/ChatStack.tsx` (NEW)
**[P2]** Native stack with:
- `ConversationList` -- `headerLargeTitle: true`
- `Chat` -- standard header
- `VoiceMode` -- `presentation: 'formSheet'`, `sheetAllowedDetents: [0.95]`, `sheetGrabberVisible: true`, `headerShown: false`

### `/home/ubuntu/homeagent/mobile/src/navigation/FamilyStack.tsx` (NEW)
**[P2]** Native stack with: FamilyManage (as home), FamilyTree, AdminMemberDetail, AdminMembers.

### `/home/ubuntu/homeagent/mobile/src/navigation/AgentsStack.tsx` (NEW)
**[P2]** Native stack with: MyAgents (home), AgentSetup, AdminAgentTemplates.

### `/home/ubuntu/homeagent/mobile/src/navigation/SettingsStack.tsx` (NEW)
**[P2]** Native stack with: Settings (home), Profile, AdminPanel.

### `/home/ubuntu/homeagent/mobile/src/navigation/AuthStack.tsx` (NEW)
**[P2]** Native stack with: Register (headerShown: false), AgentSetup.

---

### Components

### `/home/ubuntu/homeagent/mobile/src/components/VoiceButton.tsx`
**[P1]** Changes:
- Line 2: Add import `import {Ionicons} from '@expo/vector-icons';`
- Line 2: Add import `import * as Haptics from 'expo-haptics';`
- Line 18-19: Wrap onPress with haptic: `onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); onPress(); }}`
- Line 26: Replace `{recording ? '●' : 'mic'}` with `<Ionicons name={recording ? 'stop' : 'mic'} size={20} color={recording ? '#FFFFFF' : colors.primary} />`
- Lines 48-52 (icon styles): Remove `fontSize: 14` and text-based styles; the icon is now a vector component.
- Replace all hardcoded colors with theme imports.

### `/home/ubuntu/homeagent/mobile/src/components/ChatInput.tsx`
**[P1]** Changes:
- Add imports: `import {Ionicons} from '@expo/vector-icons';`, `import * as Haptics from 'expo-haptics';`, `import {colors} from '../theme';`
- Line 219: Replace `+` with `<Ionicons name="image-outline" size={22} color={disabled || recording ? colors.disabledText : colors.primary} />`
- Lines 234-239: Replace the send button content. The button becomes a 36x36 circle (not the wide pill it is now). Replace line 238 `<Text style={styles.sendText}>Send</Text>` with `<Ionicons name="arrow-up" size={20} color="#FFFFFF" />`
- Adjust `sendButton` style: change from `paddingHorizontal: 14, minHeight: 44` to `width: 36, height: 36, borderRadius: 18`
- In `handleSend` function, add `Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);` at the start.
- In `handleVoicePress`, add `Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);` at the start.
- Replace all hardcoded color strings with `colors.*` tokens.

### `/home/ubuntu/homeagent/mobile/src/components/MessageBubble.tsx`
**[P1]** Replace hardcoded colors:
- Line 77: `'#007AFF'` -> `colors.userBubble`
- Line 81: `'#E9E9EB'` -> `colors.assistantBubble`
- Line 89: `'#FFFFFF'` -> `colors.userBubbleText`
- Line 92: `'#000000'` -> `colors.assistantBubbleText`

**[P3]** Major enhancement:
- Add markdown rendering (wrap `message.content` in `<Markdown>` component for assistant messages)
- Add responsive image sizing: replace fixed `width: 150, height: 150` (line 101-102) with `width: Dimensions.get('window').width * 0.6, aspectRatio: 1, maxWidth: 250`
- Add timestamp display (requires adding `created_at` to the Props interface)

### `/home/ubuntu/homeagent/mobile/src/components/ConversationItem.tsx`
**[P1]** Changes:
- Add imports: `import {Ionicons} from '@expo/vector-icons';`, `import {Avatar} from './ui/Avatar';`, `import {colors} from '../theme';`
- Restructure the layout. Currently it is a single row with title + date. New layout:
  ```
  [Avatar(40x40)] [  Title (bold, 1 line)        ] [date]
                   [  Subtitle preview (gray, 1 line)  ] [chevron]
  ```
- The `conversation` prop currently does not contain a `lastMessage` field. For now, use a placeholder approach: show "Tap to open" as subtitle, or show no subtitle. The subtitle can be populated later when the backend adds last_message to conversation list responses.
- Add `Ionicons name="chevron-forward" size={16} color={colors.chevron}` at the end.
- Replace all hardcoded colors with theme tokens.
- Increase `paddingVertical` from 14 to 16 for better touch target.

### `/home/ubuntu/homeagent/mobile/src/components/ImageAttachment.tsx`
**[P1]** Changes:
- Line 33: Replace `<Text style={styles.removeText}>X</Text>` with `<Ionicons name="close" size={12} color="#FFFFFF" />`
- Line 22: Replace `<Text style={styles.overlayText}>...</Text>` with `<ActivityIndicator size="small" color="#FFFFFF" />`
- Line 27: Replace `<Text style={styles.overlayText}>!</Text>` with `<Ionicons name="alert-circle" size={20} color="#FFFFFF" />`

---

### Screens

### `/home/ubuntu/homeagent/mobile/src/screens/RegisterScreen.tsx`
**[P1]** Changes:
- Add imports: `import {LinearGradient} from 'expo-linear-gradient';`, `import {Ionicons} from '@expo/vector-icons';`, `import * as Haptics from 'expo-haptics';`, `import {colors, typography} from '../theme';`
- Lines 245-248, 293-296, 371-374, 421-424: Replace text "Back" with `<><Ionicons name="arrow-back" size={16} color={colors.primary} /> Back</>` and wrap in a flexDirection row.
- Add haptic feedback to all button onPress handlers: `handleMemberRegister`, `handleOwnerSignup`, `handleConfirm`, `handleLogin`.
- Replace all hardcoded colors with theme tokens.

**[P2]** Screen navigation type changes from `RootStackParamList` to `AuthStackParamList`. Update line 14 type import and line 20 type annotation.
- Lines 59, 119, 154: Replace `navigation.reset({index: 0, routes: [{name: 'ConversationList'}]})` -- in the new architecture, bootstrap will automatically switch to MainTabNavigator. These resets change to simply calling `actions.bootstrap()` (the conditional rendering in AppNavigator handles the rest).

### `/home/ubuntu/homeagent/mobile/src/screens/ConversationListScreen.tsx`
**[P1]** Changes:
- Add imports: `import {Ionicons} from '@expo/vector-icons';`, `import * as Haptics from 'expo-haptics';`, `import {colors} from '../theme';`
- Lines 34-39 (headerRight): Replace `<Text style={styles.headerButton}>Settings</Text>` with `<Ionicons name="settings-outline" size={22} color={colors.primary} />`
- Lines 131-132 (FAB): Replace `<Text style={styles.fabText}>+</Text>` with `<Ionicons name="add" size={28} color="#FFFFFF" />`
- Line 97: Add haptic on new chat: `Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);`
- Replace all hardcoded colors with theme tokens.

**[P2]** Navigation type changes to `ChatStackParamList`. Remove `headerRight` settings button (settings now in tab). Add `headerLargeTitle: true` in screen options.

### `/home/ubuntu/homeagent/mobile/src/screens/ChatScreen.tsx`
**[P1]** Changes:
- Line 55: Replace `<Text style={{fontSize: 22}}>&#9881;</Text>` with `<Ionicons name="ellipsis-horizontal" size={22} color={colors.primary} />`
- Line 237: Replace `color="#007AFF"` with `color={colors.primary}`
- Line 276: Replace `color: '#FF3B30'` with `color: colors.destructive`
- Replace all hardcoded colors with theme tokens.

**[P2]** Navigation type changes to `ChatStackParamList`. Header right becomes an ellipsis menu or voice mode button. Settings navigation is removed (it is now a tab).

**[P3]** Major changes:
- Import `TypingIndicator`, `DaySeparator`, `ScrollToBottomButton`
- Lines 162-165: When streaming starts with empty content, render `<TypingIndicator />` instead of an empty message bubble. Once first `text_delta` arrives, replace with real message.
- Add `ScrollToBottomButton` that appears when user scrolls up more than 1 screen height. Track scroll position via `onScroll` prop on FlatList.
- Add day separators between messages of different dates. This requires processing messages array to insert separator items.
- Lines 106-109: Replace setTimeout scroll hack with `maintainVisibleContentPosition={{minIndexForVisible: 0}}` prop on FlatList (RN 0.72+, supported).

### `/home/ubuntu/homeagent/mobile/src/screens/SettingsScreen.tsx`
**[P1]** Changes:
- Add imports: `import {Ionicons} from '@expo/vector-icons';`, `import * as Haptics from 'expo-haptics';`, `import {colors, typography} from '../theme';`, `import {SectionHeader, SettingsRow, ToggleRow, PrimaryButton, Avatar} from '../components/ui';`
- Replace lines 115-117 (ACCOUNT section header) with `<SectionHeader title="ACCOUNT" />`
- Replace all sectionHeader/sectionHeaderText pairs (5 occurrences) with `<SectionHeader>`
- Add Avatar component at top showing user initials (above the ACCOUNT section).
- Lines 134-138: Replace plain actionRow with `<SettingsRow icon="person-outline" label="Edit My Profile" onPress={...} />`
- Lines 139-143: Replace with `<SettingsRow icon="apps-outline" label="My Agents" onPress={...} />`
- Lines 150-154: Replace adminPanelButton with `<SettingsRow icon="shield-checkmark-outline" label="Admin Panel" onPress={...} />`
- Lines 168-173: Replace tap-to-cycle sharing level with `<SegmentedControl values={['None', 'Basic', 'Full']} selectedIndex={...} onChange={...} />` (from `@react-native-segmented-control/segmented-control`)
- Lines 174-203: Replace all toggle rows with `<ToggleRow>` components
- Lines 218-220: Replace logoutButton with `<PrimaryButton title="Log Out" variant="destructive" onPress={handleLogout} />`
- Replace all hardcoded colors with theme tokens.

**[P2]** Navigation type changes to `SettingsStackParamList`. Remove the navigation to Settings from Chat header (Settings is now a tab).

### `/home/ubuntu/homeagent/mobile/src/screens/AdminPanelScreen.tsx`
**[P1]** Changes -- icon replacements:
- Add import: `import {Ionicons} from '@expo/vector-icons';`, `import {colors} from '../theme';`
- Line 47: Replace `<Text style={styles.actionIcon}>👥</Text>` with `<Ionicons name="people-outline" size={24} color={colors.primary} style={{width: 32, textAlign: 'center', marginRight: 14}} />`
- Line 52, 64, 76: Replace `<Text style={styles.chevron}>›</Text>` with `<Ionicons name="chevron-forward" size={18} color={colors.chevron} />`
- Line 59: Replace `🌳` with `<Ionicons name="git-branch-outline" size={24} ... />`
- Line 68: Replace `🏠` with `<Ionicons name="home-outline" size={24} ... />`
- Line 84: Replace `🔑` with `<Ionicons name="key-outline" size={24} ... />`
- Line 101: Replace `🤖` with `<Ionicons name="hardware-chip-outline" size={24} ... />`
- Line 115: Replace `ℹ️` with `<Ionicons name="information-circle-outline" size={24} ... />`
- Replace all hardcoded colors with theme tokens.
- **Bug fix:** Line 99 navigates to `AdminMembers` for "Agent Configurations" -- this is a duplicate of line 45. This should either navigate to `AdminAgentTemplates` or be removed.

### `/home/ubuntu/homeagent/mobile/src/screens/AdminMembersScreen.tsx`
**[P1]** Changes:
- Add import: `import {Ionicons} from '@expo/vector-icons';`, `import {Avatar} from '../components/ui/Avatar';`, `import {colors} from '../theme';`
- Line 64: Replace `<Text style={styles.chevron}>›</Text>` with `<Ionicons name="chevron-forward" size={18} color={colors.chevron} />`
- Add `<Avatar name={item.display_name} size={36} />` before `memberInfo` in the render item.
- Replace all hardcoded colors with theme tokens.

### `/home/ubuntu/homeagent/mobile/src/screens/AdminMemberDetailScreen.tsx`
**[P1]** Changes:
- Line 151: Replace inline style `{fontSize: 16, color: '#8E8E93'}` with `{...typography.body, color: colors.textSecondary}`.
- Replace all hardcoded colors with theme tokens.
- Replace SectionHeader/saveButton/deleteButton patterns with shared components.

### `/home/ubuntu/homeagent/mobile/src/screens/ProfileScreen.tsx`
**[P1]** Replace all hardcoded colors with theme tokens. Replace saveButton with `<PrimaryButton>`.

### `/home/ubuntu/homeagent/mobile/src/screens/FamilyTreeScreen.tsx`
**[P1]** Changes:
- Line 160, 223: Replace text chevron `›` and checkmark `✓` with `<Ionicons name="chevron-forward" .../>` and `<Ionicons name="checkmark" .../>`
- Replace all hardcoded colors with theme tokens.

### `/home/ubuntu/homeagent/mobile/src/screens/FamilyManageScreen.tsx`
**[P1]** Replace all hardcoded colors with theme tokens. Replace buttons with `<PrimaryButton>`.

### `/home/ubuntu/homeagent/mobile/src/screens/MyAgentsScreen.tsx`
**[P1]** Replace all hardcoded colors with theme tokens. Already one of the better-designed screens.

### `/home/ubuntu/homeagent/mobile/src/screens/AgentSetupScreen.tsx`
**[P1]** Replace all hardcoded colors with theme tokens. This screen is the best-designed already; minimal changes.

### `/home/ubuntu/homeagent/mobile/src/screens/AdminAgentTemplatesScreen.tsx`
**[P1]** Replace all hardcoded colors with theme tokens.

### `/home/ubuntu/homeagent/mobile/src/screens/VoiceModeScreen.tsx`
**[P1]** Changes:
- Add import: `import {Ionicons} from '@expo/vector-icons';`, `import * as Haptics from 'expo-haptics';`, `import {colors} from '../theme';`
- Line 259: Replace `<Text style={styles.micIcon}>{recording ? 'STOP' : 'MIC'}</Text>` with `<Ionicons name={recording ? 'stop' : 'mic'} size={32} color="#FFFFFF" />`
- Lines 261-264: Replace "Back to Chat" text with `<Ionicons name="close" size={24} color={colors.primary} />` and wrap in a larger touch target.
- Line 208: Add haptic `Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);` in handleMicPress.
- Replace `paddingBottom: 40` (line 318) with `paddingBottom: insets.bottom + 16` using `useSafeAreaInsets()`.
- Replace all hardcoded colors with theme voiceBackground/voiceSurface tokens.

**[P2]** Change `presentation: 'formSheet'` in the ChatStack navigator options. Add `sheetAllowedDetents: [0.95]`, `sheetGrabberVisible: true`.

---

## 4. Phase 1 Detailed Spec (Foundation + Quick Wins)

### Exact Theme Token Values

See the `colors.ts`, `typography.ts`, `spacing.ts` files defined in Section 2. These are copy-paste ready.

### Exact Icon Replacements

| File | Line | Current | Replacement | Ionicons Name |
|------|------|---------|-------------|---------------|
| `VoiceButton.tsx` | 26 | `'mic'` (text) | `<Ionicons name="mic" size={20} />` | `mic` |
| `VoiceButton.tsx` | 26 | `'●'` (recording) | `<Ionicons name="stop" size={20} />` | `stop` |
| `ChatInput.tsx` | 219 | `+` (text) | `<Ionicons name="image-outline" size={22} />` | `image-outline` |
| `ChatInput.tsx` | 238 | `Send` (text) | `<Ionicons name="arrow-up" size={20} />` | `arrow-up` |
| `ChatScreen.tsx` | 55 | `&#9881;` (unicode gear) | `<Ionicons name="ellipsis-horizontal" size={22} />` | `ellipsis-horizontal` |
| `ConversationListScreen.tsx` | 38 | `Settings` (text) | `<Ionicons name="settings-outline" size={22} />` | `settings-outline` |
| `ConversationListScreen.tsx` | 132 | `+` (text) | `<Ionicons name="add" size={28} />` | `add` |
| `AdminPanelScreen.tsx` | 47 | `👥` (emoji) | `<Ionicons name="people-outline" size={24} />` | `people-outline` |
| `AdminPanelScreen.tsx` | 59 | `🌳` (emoji) | `<Ionicons name="git-branch-outline" size={24} />` | `git-branch-outline` |
| `AdminPanelScreen.tsx` | 68 | `🏠` (emoji) | `<Ionicons name="home-outline" size={24} />` | `home-outline` |
| `AdminPanelScreen.tsx` | 84 | `🔑` (emoji) | `<Ionicons name="key-outline" size={24} />` | `key-outline` |
| `AdminPanelScreen.tsx` | 101 | `🤖` (emoji) | `<Ionicons name="hardware-chip-outline" size={24} />` | `hardware-chip-outline` |
| `AdminPanelScreen.tsx` | 115 | `ℹ️` (emoji) | `<Ionicons name="information-circle-outline" size={24} />` | `information-circle-outline` |
| `AdminPanelScreen.tsx` | 52,64,76,106 | `›` (text chevron) | `<Ionicons name="chevron-forward" size={18} />` | `chevron-forward` |
| `AdminMembersScreen.tsx` | 64 | `›` (text chevron) | `<Ionicons name="chevron-forward" size={18} />` | `chevron-forward` |
| `FamilyTreeScreen.tsx` | 160 | `›` (text chevron) | `<Ionicons name="chevron-forward" size={18} />` | `chevron-forward` |
| `FamilyTreeScreen.tsx` | 223 | `✓` (text checkmark) | `<Ionicons name="checkmark" size={18} />` | `checkmark` |
| `VoiceModeScreen.tsx` | 259 | `MIC`/`STOP` (text) | `<Ionicons name="mic"/"stop" size={32} />` | `mic` / `stop` |
| `VoiceModeScreen.tsx` | 264 | `Back to Chat` (text) | `<Ionicons name="close" size={24} />` | `close` |
| `ImageAttachment.tsx` | 33 | `X` (text) | `<Ionicons name="close" size={12} />` | `close` |

### Files That Need Color Token Migration

Every file below contains hardcoded color literals that must be replaced with `import {colors} from '../theme'` (or `'../../theme'` depending on depth):

1. `/home/ubuntu/homeagent/mobile/src/navigation/AppNavigator.tsx` -- `#007AFF`, `#FFFFFF`, `#333`
2. `/home/ubuntu/homeagent/mobile/src/components/ChatInput.tsx` -- `#C6C6C8`, `#FFFFFF`, `#007AFF`, `#B0B0B0`, `#F9F9F9`, `#000000`, `#8E8E93`, `#FF3B30`, `#E9E9EB`
3. `/home/ubuntu/homeagent/mobile/src/components/MessageBubble.tsx` -- `#007AFF`, `#E9E9EB`, `#FFFFFF`, `#000000`
4. `/home/ubuntu/homeagent/mobile/src/components/VoiceButton.tsx` -- `#E9E9EB`, `#FF3B30`, `#007AFF`, `#FFFFFF`, `#B0B0B0`
5. `/home/ubuntu/homeagent/mobile/src/components/ConversationItem.tsx` -- `#E5E5EA`, `#FFFFFF`, `#000000`, `#8E8E93`
6. `/home/ubuntu/homeagent/mobile/src/components/ImageAttachment.tsx` -- `#FFFFFF`
7. `/home/ubuntu/homeagent/mobile/src/screens/RegisterScreen.tsx` -- `#FFFFFF`, `#000000`, `#8E8E93`, `#C6C6C8`, `#F9F9F9`, `#007AFF`, `#B0B0B0`
8. `/home/ubuntu/homeagent/mobile/src/screens/ConversationListScreen.tsx` -- `#F2F2F7`, `#007AFF`, `#8E8E93`, `#AEAEB2`, `#FFFFFF`, `#000`
9. `/home/ubuntu/homeagent/mobile/src/screens/ChatScreen.tsx` -- `#FFFFFF`, `#007AFF`, `#FF3B30`
10. `/home/ubuntu/homeagent/mobile/src/screens/SettingsScreen.tsx` -- `#F2F2F7`, `#8E8E93`, `#FFFFFF`, `#E5E5EA`, `#000000`, `#007AFF`, `#FF3B30`, `#AEAEB2`
11. `/home/ubuntu/homeagent/mobile/src/screens/ProfileScreen.tsx` -- `#F2F2F7`, `#8E8E93`, `#FFFFFF`, `#E5E5EA`, `#000000`, `#007AFF`
12. `/home/ubuntu/homeagent/mobile/src/screens/AdminPanelScreen.tsx` -- `#F2F2F7`, `#8E8E93`, `#FFFFFF`, `#E5E5EA`, `#000000`, `#C7C7CC`
13. `/home/ubuntu/homeagent/mobile/src/screens/AdminMembersScreen.tsx` -- `#F2F2F7`, `#007AFF`, `#FFFFFF`, `#E5E5EA`, `#000000`, `#8E8E93`, `#C7C7CC`
14. `/home/ubuntu/homeagent/mobile/src/screens/AdminMemberDetailScreen.tsx` -- `#F2F2F7`, `#8E8E93`, `#FFFFFF`, `#E5E5EA`, `#000000`, `#007AFF`, `#FF3B30`, `#FF9500`
15. `/home/ubuntu/homeagent/mobile/src/screens/FamilyTreeScreen.tsx` -- `#F2F2F7`, `#8E8E93`, `#FFFFFF`, `#E5E5EA`, `#000000`, `#007AFF`, `#C7C7CC`
16. `/home/ubuntu/homeagent/mobile/src/screens/FamilyManageScreen.tsx` -- `#F2F2F7`, `#8E8E93`, `#FFFFFF`, `#E5E5EA`, `#000000`, `#007AFF`, `#FF3B30`
17. `/home/ubuntu/homeagent/mobile/src/screens/MyAgentsScreen.tsx` -- `#F2F2F7`, `#007AFF`, `#FFFFFF`, `#E5E5EA`, `#000000`, `#8E8E93`, `#34C759`, `#3C3C43`, `#FFE0B2`, `#E65100`, `#FAFAFA`
18. `/home/ubuntu/homeagent/mobile/src/screens/AgentSetupScreen.tsx` -- `#F2F2F7`, `#8E8E93`, `#FFFFFF`, `#E5E5EA`, `#000000`, `#C6C6C8`, `#F9F9F9`, `#007AFF`, `#EBF5FF`, `#34C759`, `#B0B0B0`
19. `/home/ubuntu/homeagent/mobile/src/screens/AdminAgentTemplatesScreen.tsx` -- same pattern
20. `/home/ubuntu/homeagent/mobile/src/screens/VoiceModeScreen.tsx` -- `#1C1C1E`, `#2C2C2E`, `#3A3A3C`, `#8E8E93`, `#FFFFFF`, `#FF453A`, `#007AFF`, `#48484A`

### Reusable Component APIs (Props)

**SectionHeader:**
```ts
interface SectionHeaderProps {
  title: string;
  rightElement?: React.ReactNode;
}
```
Rendering: `<View style={{paddingHorizontal: spacing.lg, paddingTop: spacing.xxl, paddingBottom: spacing.sm}}><Text style={{...typography.footnote, color: colors.textSecondary}}>{title}</Text>{rightElement}</View>`

**SettingsRow:**
```ts
interface SettingsRowProps {
  icon?: React.ComponentProps<typeof Ionicons>['name'];
  iconColor?: string;
  label: string;
  sublabel?: string;
  value?: string;
  showChevron?: boolean;
  onPress?: () => void;
  destructive?: boolean;
}
```
Rendering: White row, 16px horizontal padding, 14px vertical padding, hairline bottom border. Icon (24x24, 14px marginRight) + label/sublabel column (flex: 1) + value text + optional chevron-forward (18px, chevron color). onPress wraps with `Haptics.selectionAsync()`.

**ToggleRow:**
```ts
interface ToggleRowProps {
  label: string;
  sublabel?: string;
  value: boolean;
  onValueChange: (value: boolean) => void;
  disabled?: boolean;
}
```
Rendering: White row matching SettingsRow layout but with `<Switch>` instead of chevron. `trackColor={{false: colors.separator, true: colors.success}}`.

**PrimaryButton:**
```ts
interface PrimaryButtonProps {
  title: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  variant?: 'primary' | 'secondary' | 'destructive';
  icon?: React.ComponentProps<typeof Ionicons>['name'];
  style?: ViewStyle;
}
```
Rendering: height 48, borderRadius 10, centered. Primary: bg `colors.primary`, text white. Secondary: bg white, border 2px `colors.primary`, text `colors.primary`. Destructive: bg `colors.destructive`, text white. Loading: replace text with ActivityIndicator. Disabled: opacity 0.6. Haptic on press.

**Avatar:**
```ts
interface AvatarProps {
  name: string;
  size?: number;
  color?: string;
}
```
Rendering: Circle with `size` (default 40), background color derived from name hash (pick from predefined palette of 8 colors: `['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F']`). White text, first character uppercase, font size = size * 0.4.

**EmptyState:**
```ts
interface EmptyStateProps {
  icon?: React.ComponentProps<typeof Ionicons>['name'];
  title: string;
  subtitle?: string;
  actionLabel?: string;
  onAction?: () => void;
}
```
Rendering: Centered, paddingTop 80. Icon (48px, textSecondary color) + title (typography.headline) + subtitle (typography.callout, textSecondary) + optional PrimaryButton.

---

## 5. Phase 2 Detailed Spec (Navigation Overhaul)

### Tab Navigator Configuration

```ts
// MainTabNavigator.tsx
import {createBottomTabNavigator} from '@react-navigation/bottom-tabs';
import {Ionicons} from '@expo/vector-icons';
import {colors, typography} from '../theme';
import {useSession} from '../store';

const Tab = createBottomTabNavigator<MainTabParamList>();

export function MainTabNavigator() {
  const {isOwnerOrAdmin} = useSession();

  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,   // each tab stack has its own headers
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textSecondary,
        tabBarLabelStyle: {fontSize: 11, fontWeight: '500'},
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.separator,
        },
      }}>
      <Tab.Screen
        name="ChatsTab"
        component={ChatStack}
        options={{
          tabBarLabel: 'Chats',
          tabBarIcon: ({color, size}) => (
            <Ionicons name="chatbubbles-outline" size={size} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="FamilyTab"
        component={FamilyStack}
        options={{
          tabBarLabel: 'Family',
          tabBarIcon: ({color, size}) => (
            <Ionicons name="people-outline" size={size} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="AgentsTab"
        component={AgentsStack}
        options={{
          tabBarLabel: 'Agents',
          tabBarIcon: ({color, size}) => (
            <Ionicons name="sparkles-outline" size={size} color={color} />
          ),
        }}
      />
      <Tab.Screen
        name="SettingsTab"
        component={SettingsStack}
        options={{
          tabBarLabel: 'Settings',
          tabBarIcon: ({color, size}) => (
            <Ionicons name="settings-outline" size={size} color={color} />
          ),
        }}
      />
    </Tab.Navigator>
  );
}
```

### Auth Flow Changes

Currently, the app uses a single Stack.Navigator with conditional `initialRouteName` (line 77-78 of AppNavigator.tsx). After Phase 2:

```ts
// AppNavigator.tsx (simplified)
function AppContent() {
  const {session, actions} = useSession();

  useEffect(() => { actions.bootstrap(); }, [actions]);

  // Auth expiry listener stays the same

  if (session.status === 'loading') {
    return <SplashScreen />;
  }

  return (
    <NavigationContainer>
      {session.status === 'authenticated'
        ? <MainTabNavigator />
        : <AuthStack />}
    </NavigationContainer>
  );
}
```

The conditional rendering pattern (instead of resetting navigation) means:
- When `actions.bootstrap()` succeeds, `session.status` changes to `authenticated`, and React re-renders `MainTabNavigator` automatically
- When `actions.logout()` runs, `session.status` changes to `unauthenticated`, and React re-renders `AuthStack` automatically
- No more `navigation.reset({index: 0, routes: [...]})` calls needed in RegisterScreen

### Screen-to-Stack Assignments

| Screen | Current Stack | New Stack | Notes |
|--------|--------------|-----------|-------|
| Register | Root | AuthStack | headerShown: false |
| AgentSetup | Root | AuthStack (onboarding) + AgentsStack (re-configure) | Registered in both stacks |
| ConversationList | Root | ChatStack | Large title, home screen of ChatsTab |
| Chat | Root | ChatStack | Push from ConversationList |
| VoiceMode | Root | ChatStack | formSheet presentation |
| Settings | Root | SettingsStack | Home screen of SettingsTab |
| Profile | Root | SettingsStack | Push |
| AdminPanel | Root | SettingsStack | Push (admin only) |
| AdminMembers | Root | FamilyStack | Push (admin only) |
| AdminMemberDetail | Root | FamilyStack | Push |
| FamilyTree | Root | FamilyStack | Push |
| FamilyManage | Root | FamilyStack | Home screen of FamilyTab |
| MyAgents | Root | AgentsStack | Home screen of AgentsTab |
| AdminAgentTemplates | Root | AgentsStack | Push (admin only) |

### VoiceMode formSheet Presentation

In `ChatStack.tsx`:
```ts
<Stack.Screen
  name="VoiceMode"
  component={VoiceModeScreen}
  options={{
    headerShown: false,
    presentation: 'formSheet',
    sheetAllowedDetents: [0.95],
    sheetGrabberVisible: true,
    sheetCornerRadius: 20,
    gestureEnabled: true,
  }}
/>
```

This uses React Navigation v7's native formSheet support. On iOS, this slides up as a native sheet with a grabber. On Android, it falls back to a modal presentation. The dark background of VoiceModeScreen looks natural inside the sheet.

VoiceModeScreen's "Back to Chat" button (line 261-264) changes to an X icon in the top-right corner, or users can swipe down to dismiss (native sheet gesture).

### Param List Updates

Every screen file currently imports `RootStackParamList` from `../navigation/AppNavigator`. These imports all change:

| File | Current Import | New Import |
|------|---------------|------------|
| `RegisterScreen.tsx` | `RootStackParamList, 'Register'` | `AuthStackParamList, 'Register'` from `../navigation/types` |
| `ConversationListScreen.tsx` | `RootStackParamList, 'ConversationList'` | `ChatStackParamList, 'ConversationList'` from `../navigation/types` |
| `ChatScreen.tsx` | `RootStackParamList, 'Chat'` | `ChatStackParamList, 'Chat'` from `../navigation/types` |
| `VoiceModeScreen.tsx` | `RootStackParamList, 'VoiceMode'` | `ChatStackParamList, 'VoiceMode'` from `../navigation/types` |
| `SettingsScreen.tsx` | `RootStackParamList, 'Settings'` | `SettingsStackParamList, 'SettingsHome'` from `../navigation/types` |
| `ProfileScreen.tsx` | `RootStackParamList, 'Profile'` | `SettingsStackParamList, 'Profile'` from `../navigation/types` |
| `AdminPanelScreen.tsx` | `RootStackParamList, 'AdminPanel'` | `SettingsStackParamList, 'AdminPanel'` from `../navigation/types` |
| `AdminMembersScreen.tsx` | `RootStackParamList, 'AdminMembers'` | `FamilyStackParamList, 'AdminMembers'` from `../navigation/types` |
| `AdminMemberDetailScreen.tsx` | `RootStackParamList, 'AdminMemberDetail'` | `FamilyStackParamList, 'AdminMemberDetail'` from `../navigation/types` |
| `FamilyTreeScreen.tsx` | `RootStackParamList, 'FamilyTree'` | `FamilyStackParamList, 'FamilyTree'` from `../navigation/types` |
| `FamilyManageScreen.tsx` | `RootStackParamList, 'FamilyManage'` | `FamilyStackParamList, 'FamilyManage'` from `../navigation/types` |
| `MyAgentsScreen.tsx` | `RootStackParamList, 'MyAgents'` | `AgentsStackParamList, 'MyAgents'` from `../navigation/types` |
| `AgentSetupScreen.tsx` | `RootStackParamList, 'AgentSetup'` | `AgentsStackParamList, 'AgentSetup'` from `../navigation/types` |

**Cross-tab navigation:** SettingsScreen currently navigates to `Profile`, `MyAgents`, and `AdminPanel`. After the restructure:
- `Profile` stays in SettingsStack -- no change
- `MyAgents` is now in AgentsTab -- SettingsRow for "My Agents" should switch to the Agents tab instead of pushing a screen. Use `navigation.getParent()?.navigate('AgentsTab')`.
- `AdminPanel` stays in SettingsStack -- no change

---

## 6. Phase 3 Detailed Spec (Chat Experience)

### MessageBubble Redesign

New style values for `/home/ubuntu/homeagent/mobile/src/components/MessageBubble.tsx`:

```ts
// Current -> New
userBubble.backgroundColor: '#007AFF' -> colors.userBubble (no change in value)
assistantBubble.backgroundColor: '#E9E9EB' -> colors.assistantBubble ('#F0F0F5')
// NEW: add subtle border to assistant bubble
assistantBubble.borderWidth: 1,
assistantBubble.borderColor: colors.separator,
// Images: responsive sizing
messageImage.width: '100%', (remove fixed 150)
messageImage.height: undefined,
messageImage.aspectRatio: 1,
messageImage.maxWidth: 250,
messageImage.borderRadius: 12,
```

**Markdown integration:** Use `react-native-markdown-display` library.

In MessageBubble:
```tsx
import Markdown from 'react-native-markdown-display';

const markdownStyles = {
  body: {fontSize: 16, lineHeight: 22, color: colors.assistantBubbleText},
  code_block: {backgroundColor: '#F0F0F0', borderRadius: 6, padding: 8, fontSize: 14},
  code_inline: {backgroundColor: '#F0F0F0', borderRadius: 3, paddingHorizontal: 4, fontSize: 14},
  link: {color: colors.primary},
  heading1: {fontSize: 20, fontWeight: '700', marginBottom: 4},
  heading2: {fontSize: 18, fontWeight: '600', marginBottom: 4},
  bullet_list: {marginVertical: 4},
  ordered_list: {marginVertical: 4},
};

// In the render:
{isUser ? (
  <Text style={[styles.text, styles.userText]} selectable>{message.content}</Text>
) : (
  <Markdown style={markdownStyles}>{message.content}</Markdown>
)}
```

User messages stay as plain Text (users don't type markdown). Only assistant messages get markdown rendering.

### Typing Indicator Component

`/home/ubuntu/homeagent/mobile/src/components/TypingIndicator.tsx`:

```tsx
import React from 'react';
import {View, StyleSheet} from 'react-native';
import Animated, {
  useAnimatedStyle,
  withRepeat,
  withSequence,
  withTiming,
  withDelay,
} from 'react-native-reanimated';
import {colors} from '../theme';

export function TypingIndicator() {
  const createDotStyle = (delay: number) => {
    return useAnimatedStyle(() => ({
      opacity: withRepeat(
        withDelay(
          delay,
          withSequence(
            withTiming(1, {duration: 400}),
            withTiming(0.3, {duration: 400}),
          ),
        ),
        -1,
        false,
      ),
    }));
  };

  const dot1 = createDotStyle(0);
  const dot2 = createDotStyle(200);
  const dot3 = createDotStyle(400);

  return (
    <View style={styles.container}>
      <View style={styles.bubble}>
        <Animated.View style={[styles.dot, dot1]} />
        <Animated.View style={[styles.dot, dot2]} />
        <Animated.View style={[styles.dot, dot3]} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {marginVertical: 4, marginHorizontal: 12, alignItems: 'flex-start'},
  bubble: {
    flexDirection: 'row',
    backgroundColor: colors.assistantBubble,
    borderRadius: 18,
    borderBottomLeftRadius: 4,
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 4,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.textSecondary,
  },
});
```

### Day Separator Component

`/home/ubuntu/homeagent/mobile/src/components/DaySeparator.tsx`:

```tsx
interface DaySeparatorProps {
  date: string; // ISO
}

function formatSeparatorDate(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  if (date.toDateString() === today.toDateString()) return 'Today';
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return date.toLocaleDateString(undefined, {month: 'short', day: 'numeric'});
}

// Renders: thin gray line --- "Today" --- thin gray line
// centered, 16px vertical margin, caption1 typography, textTertiary color
```

### Scroll-to-Bottom Button

`/home/ubuntu/homeagent/mobile/src/components/ScrollToBottomButton.tsx`:

```tsx
interface ScrollToBottomButtonProps {
  visible: boolean;
  onPress: () => void;
}
// Positioned: absolute, bottom 8, right 16 (above ChatInput)
// Size: 36x36 circle, bg white, shadow, border 1px separator
// Icon: Ionicons "chevron-down" size 20, color textSecondary
// Animation: Reanimated FadeIn.duration(200) / FadeOut.duration(200)
// entering={FadeIn} exiting={FadeOut}
```

Integration in ChatScreen:
```tsx
const [showScrollButton, setShowScrollButton] = useState(false);

// On FlatList:
onScroll={(event) => {
  const {contentOffset, contentSize, layoutMeasurement} = event.nativeEvent;
  const distanceFromBottom = contentSize.height - contentOffset.y - layoutMeasurement.height;
  setShowScrollButton(distanceFromBottom > layoutMeasurement.height);
}}
scrollEventThrottle={100}

// Before ChatInput:
<ScrollToBottomButton
  visible={showScrollButton}
  onPress={() => flatListRef.current?.scrollToEnd({animated: true})}
/>
```

### ChatInput Redesign -- Send/Mic Swap Behavior

The WhatsApp-style pattern:
- When text input is empty AND no attachments: show mic button (no send button visible)
- When text input has content OR attachments exist: show send button (mic button hidden)

Implementation in ChatInput:
```tsx
const showSend = text.trim().length > 0 || attachments.length > 0;

// In the input row, after the TextInput:
{showSend ? (
  <TouchableOpacity
    style={styles.sendButton}
    onPress={handleSend}
    disabled={disabled}>
    <Ionicons name="arrow-up" size={20} color="#FFFFFF" />
  </TouchableOpacity>
) : (
  <VoiceButton
    onPress={handleVoicePress}
    disabled={disabled}
    recording={recording}
  />
)}
```

This removes the current layout where send and mic buttons are always both visible. The VoiceButton is already the correct 44x44 size. The send button becomes a 36x36 blue circle matching iMessage's send button.

### Recording Animation

In VoiceButton, when `recording` is true, add a pulsing ring around the button:

```tsx
import Animated, {
  useAnimatedStyle,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';

// When recording, render an outer ring that pulses
const pulseStyle = useAnimatedStyle(() => ({
  transform: [{
    scale: withRepeat(
      withSequence(
        withTiming(1.3, {duration: 800}),
        withTiming(1.0, {duration: 800}),
      ),
      -1,
    ),
  }],
  opacity: withRepeat(
    withSequence(
      withTiming(0.3, {duration: 800}),
      withTiming(0, {duration: 800}),
    ),
    -1,
  ),
}));

// Render: Animated.View with absolute position, same size + 8px extra,
// borderRadius matching, red background, behind the button
```

---

## 7. Risk Assessment

### Breaking Changes

1. **Phase 2 navigation restructure is the highest-risk change.** Every screen imports `RootStackParamList` and uses `navigation.navigate('ScreenName')`. When screens move to different stacks, cross-stack navigation calls will break at compile time (TypeScript catches these). Specifically:
   - `SettingsScreen` navigates to `Profile`, `MyAgents`, `AdminPanel` -- MyAgents moves to AgentsTab
   - `AdminPanelScreen` navigates to `AdminMembers`, `FamilyTree`, `FamilyManage` -- all move to FamilyTab
   - `RegisterScreen` calls `navigation.reset()` to `ConversationList` and `AgentSetup` -- both change to conditional rendering

   **Mitigation:** Convert navigation type imports first, fix all TypeScript errors, then test every navigation path manually. Cross-tab navigation uses `navigation.getParent()?.navigate()`.

2. **react-native-reanimated requires babel plugin and Metro cache clear.** After installing and updating babel.config.js, must run `npx expo start --clear` to clear Metro bundler cache. Forgetting this causes cryptic runtime errors.

3. **@expo/vector-icons bundle size.** Ionicons alone adds ~300KB to the JS bundle. This is acceptable for this app. If size becomes a concern, use `createIconSetFromIcoMoon` for custom icon subset.

4. **react-native-markdown-display may have rendering quirks.** Complex markdown (nested lists, tables) may not render perfectly. Test with actual assistant responses. Fallback: use `selectable` plain Text and add markdown support incrementally.

### Screens Needing Backend Changes

- **ConversationItem enhancement (last message preview):** The current `/api/conversations` endpoint returns `Conversation` objects with `title`, `created_at`, `updated_at` but NO last message content. Adding a `last_message_preview` field to the API response would require a backend change in `/home/ubuntu/homeagent/backend/app/` routes. For Phase 1, use the conversation title as the primary line and skip the preview line. File a backend task to add `last_message_preview` to the conversations list endpoint.

- **Message timestamps in chat:** The `Message` type has `created_at` but `ChatScreen` currently strips it when mapping to `DisplayMessage` (lines 71-76, 91-96). This is a frontend-only fix -- just include `created_at` in the mapping. No backend change needed.

- **Everything else is frontend-only.** The navigation restructure, theme system, icons, haptics, animations -- none require backend changes.

### Testing Strategy

**After Phase 1 (Foundation):**
- Verify all icons render correctly on both iOS and Android
- Verify haptic feedback fires (physical device only, not simulator)
- Verify no hardcoded color values remain (search for `#` followed by 3 or 6 hex chars in .tsx files)
- Verify theme tokens are correct -- check each screen visually
- Verify the app builds without errors (`npx expo start --clear`)
- Run the existing flow: Register -> AgentSetup -> ConversationList -> Chat -> Settings -> Profile -> Back

**After Phase 2 (Navigation):**
- Verify tab bar appears with 4 tabs, correct icons, correct labels
- Verify each tab opens the correct home screen
- Verify back navigation works within each tab stack
- Verify auth flow: logout -> Register appears (no tabs), login -> tabs appear
- Verify auth expiry: force 401 -> tabs disappear, Register appears
- Verify VoiceMode opens as formSheet and can be dismissed by swipe-down
- Verify cross-tab navigation: Settings "My Agents" switches to Agents tab
- Verify FamilyTab is hidden for non-admin users (if implemented)
- Verify deep linking still works (if used)

**After Phase 3 (Chat):**
- Verify typing indicator appears when streaming starts
- Verify typing indicator disappears when first text_delta arrives
- Verify day separators appear between messages from different days
- Verify scroll-to-bottom button appears when scrolled up, disappears when at bottom
- Verify markdown renders: bold, italic, code blocks, links, lists
- Verify links in markdown are tappable
- Verify images render responsively (not overflowing, proper aspect ratio)
- Verify send/mic swap: mic shows when input empty, send shows when text entered
- Verify recording pulse animation on mic button
- Verify the app does not crash when switching between tabs while streaming

---

## Summary of Change Counts

| Category | New Files | Modified Files |
|----------|-----------|----------------|
| Theme system | 4 | 0 |
| UI components | 7 | 0 |
| Chat components | 3 | 0 |
| Navigation | 7 | 1 (AppNavigator.tsx) |
| Config | 0 | 2 (babel.config.js, package.json) |
| Existing screens (P1 icons/colors) | 0 | 14 |
| Existing components (P1 icons/colors) | 0 | 5 |
| Existing screens (P2 nav types) | 0 | 14 |
| Existing screens (P3 chat) | 0 | 3 |
| **Total** | **21 new files** | **20 unique modified files** |
