# Mobile Subagent — React Native (Expo)

## Scope
- You work ONLY on files under `mobile/`.
- You may READ `backend/app/routes/` to understand API contracts, but never modify backend code.
- When adding or changing API calls, verify the endpoint exists in the backend routes first.

## Tech Stack
- **Expo SDK 54+**, managed workflow, React Native 0.81+
- **React 19**, strict TypeScript 5.7+, no `any` — use `unknown` + type narrowing
- **React Navigation v7** (native-stack) — migrate to Expo Router when ready
- **expo-secure-store** for all sensitive data (tokens, credentials)
- Path aliases: `@/*` → `src/*` (configured in tsconfig + babel)

## Project Structure

Follow a feature-based architecture:

```
mobile/
├── App.tsx                          # Root: SafeArea + ErrorBoundary + Navigation
├── app.json                         # Expo config (API base URL, plugins)
├── src/
│   ├── components/                  # Shared, reusable UI components
│   │   └── ComponentName.tsx
│   ├── features/                    # Feature modules (self-contained)
│   │   └── chat/
│   │       ├── components/          # Feature-specific components
│   │       ├── hooks/               # Feature-specific hooks
│   │       └── ChatScreen.tsx       # Screen entry point
│   ├── hooks/                       # Shared custom hooks
│   ├── navigation/
│   │   └── AppNavigator.tsx         # Navigation tree definition
│   ├── services/                    # API client, auth, SSE
│   ├── theme/                       # Colors, spacing, typography tokens
│   │   └── tokens.ts
│   ├── types/                       # Shared TypeScript interfaces
│   │   └── index.ts
│   └── utils/                       # Pure utility functions
├── __tests__/                       # Test files mirroring src/ structure
└── assets/                          # Icons, splash, images
```

### Rules
- Every screen lives inside a feature folder under `src/features/`.
- Shared components used by 2+ features go in `src/components/`.
- Components used by only one feature stay in that feature's `components/` dir.
- No circular imports between features — shared code goes in `services/`, `hooks/`, or `utils/`.

## Component Patterns

### Function Components Only
```typescript
type Props = {
  title: string;
  onPress: () => void;
  disabled?: boolean;
};

export function PrimaryButton({ title, onPress, disabled = false }: Props) {
  return (
    <TouchableOpacity style={styles.button} onPress={onPress} disabled={disabled}>
      <Text style={styles.label}>{title}</Text>
    </TouchableOpacity>
  );
}
```

### Rules
- Export named functions, not default exports (better refactoring, better imports).
- Props type defined as a `type` alias at the top of the file; export it if other components need it.
- Destructure props in the function signature with defaults for optional props.
- One component per file. File name matches component name exactly (`PrimaryButton.tsx`).

## State Management

### Local State
- Use `useState` for UI-only state (form inputs, toggle visibility, loading indicators).
- Use `useReducer` for local state with complex transitions (multi-field forms, state machines).

### Shared / Global State
- Use **Zustand** for state shared across screens (auth, user profile, conversation cache).
- Keep stores small and focused — one store per domain (authStore, chatStore, profileStore).
- Use selectors to subscribe to only the state slices a component needs.

```typescript
import { create } from 'zustand';

type AuthState = {
  userId: string | null;
  role: 'admin' | 'member' | null;
  setAuth: (userId: string, role: 'admin' | 'member') => void;
  clearAuth: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  userId: null,
  role: null,
  setAuth: (userId, role) => set({ userId, role }),
  clearAuth: () => set({ userId: null, role: null }),
}));
```

### Rules
- Never store sensitive data (tokens, secrets) in Zustand — use `expo-secure-store`.
- Never put API responses directly into global state without shaping them to what the UI needs.
- Keep server state and client state separate — if adopting a server cache layer, use TanStack Query (React Query).

## Styling

Use `StyleSheet.create` with a centralized theme token system.

### Theme Tokens (`src/theme/tokens.ts`)
```typescript
export const colors = {
  primary: '#007AFF',
  background: '#FFFFFF',
  surface: '#F2F2F7',
  text: '#000000',
  textSecondary: '#8E8E93',
  error: '#FF3B30',
  border: '#C6C6C8',
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
} as const;

export const typography = {
  title: { fontSize: 20, fontWeight: '600' as const },
  body: { fontSize: 16, fontWeight: '400' as const },
  caption: { fontSize: 13, fontWeight: '400' as const },
} as const;
```

### Rules
- Always reference tokens — never hardcode colors, spacing, or font sizes in components.
- Define styles with `StyleSheet.create` at the bottom of each component file.
- Use `Platform.select()` for platform-specific style differences (shadows vs elevation).
- No inline style objects in JSX — they create new objects on every render.

## Lists & Performance

### Lists
- Use **FlashList** (`@shopify/flash-list`) instead of FlatList for long or dynamic lists.
- Always provide `estimatedItemSize` to FlashList.
- Always provide `keyExtractor`.
- Wrap `renderItem` functions in `useCallback`.
- Wrap list item components in `React.memo` when items are complex.

### Memoization — Apply Deliberately
- Use `React.memo` on components that receive stable primitive props but have expensive render trees.
- Use `useCallback` only when passing callbacks to memoized children or as hook dependencies.
- Use `useMemo` only for genuinely expensive computations — not simple filters or maps on small arrays.
- If you're unsure whether to memoize, don't. Measure first.

### General Performance
- Remove all `console.*` in production (use `babel-plugin-transform-remove-console`).
- Use `useNativeDriver: true` for all Animated API calls.
- Defer heavy work with `InteractionManager.runAfterInteractions()` after navigation transitions.
- Always test performance claims in release builds, not dev mode.

## Navigation

### Current: React Navigation v7 (native-stack)
```typescript
const Stack = createNativeStackNavigator();

// Type-safe route params
export type RootStackParamList = {
  ConversationList: undefined;
  Chat: { conversationId: string; title?: string };
  Settings: undefined;
  Profile: undefined;
};
```

### Rules
- Always define a `ParamList` type for each navigator and pass it as generic.
- Use `useNavigation<NativeStackNavigationProp<RootStackParamList>>()` for typed navigation.
- Use `useRoute<RouteProp<RootStackParamList, 'Chat'>>()` for typed route params.
- Prefer native-stack (`@react-navigation/native-stack`) over JS-based stack.
- Authentication flow: use conditional rendering at root navigator level, not guard screens.

## API & Networking

### HTTP Client
- All API functions live in `src/services/api.ts`.
- Every function is typed: explicit return type, typed request body.
- Bearer token injected via shared `headers()` helper.
- 401 responses trigger global auth expiration event — never handle auth expiry per-screen.

### SSE Streaming
- SSE uses XMLHttpRequest (not fetch) for React Native compatibility.
- SSE client lives in `src/services/sse.ts`.
- Always handle all event types: `text_delta`, `message_done`, `error`.
- Clean up SSE connections on unmount (`useEffect` cleanup).

### Rules
- Never call `fetch` directly from components — always go through `api.ts`.
- Type all API responses — no casting to `any` or untyped JSON.
- Handle loading, error, and empty states for every API call in the UI.

## Error Handling

### Error Boundaries
- Wrap the root app in an `ErrorBoundary` with a full-screen fallback (restart button).
- Wrap each screen in its own `ErrorBoundary` so one crash doesn't take down the app.
- Use the `react-error-boundary` package.

### Async Errors
- Every `async` call in a component must have error handling (try/catch or `.catch`).
- Show user-facing error messages via `Alert.alert` or inline error states — never swallow errors silently.
- Log errors to console in dev; in production, send to an error tracking service.

### Rules
- Never use bare `catch (e)` without typing or narrowing — use `catch (e: unknown)`.
- API errors should surface the backend's error message when available, with a generic fallback.

## Testing

### Stack
- **Jest** with `jest-expo` preset for unit + integration tests.
- **React Native Testing Library** (`@testing-library/react-native`) for component tests.
- **Maestro** for E2E tests (YAML-based, runs on device/simulator).

### What to Test
- **Services**: API client functions (mock fetch, verify request shape and headers).
- **Hooks**: Custom hooks with `renderHook` (state transitions, side effects).
- **Components**: User-visible behavior — render, interact, assert text/state changes.
- **Screens**: Integration tests — render screen with mocked navigation and API, test user flows.

### Rules
- Test behavior, not implementation — query by text/role/testID, not component internals.
- Each new feature or screen must include tests.
- Keep tests next to source: `src/features/chat/__tests__/ChatScreen.test.tsx`.
- No snapshot tests unless explicitly requested.

## Security

- **Tokens**: Store ONLY in `expo-secure-store`. Never in AsyncStorage, state, or logs.
- **Secrets**: Never embed API keys or secrets in client code. All secrets stay on the backend.
- **Deep links**: Never pass sensitive data in deep link URLs.
- **Logging**: Never log tokens, passwords, or PII. Strip sensitive fields before any error reporting.
- **Validation**: Always validate on the backend. Client validation is for UX only.
- **HTTPS**: All network requests must use HTTPS in production (HTTP allowed for localhost in dev).

## Pre-Completion Checklist

Before considering any task done, verify:
- [ ] `npx tsc --noEmit` passes with zero errors
- [ ] No `any` types introduced
- [ ] New components use theme tokens, not hardcoded values
- [ ] New API calls are typed end-to-end (request + response)
- [ ] Loading, error, and empty states handled in UI
- [ ] SSE connections cleaned up on unmount
- [ ] No sensitive data in logs or state stores
- [ ] Tests written for new logic
