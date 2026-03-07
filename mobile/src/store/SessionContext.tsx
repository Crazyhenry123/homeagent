import React, {createContext, useContext, useMemo, useReducer} from 'react';
import type {
  AgentTypeInfo,
  AvailableAgent,
  AgentConfig,
  Conversation,
  Family,
  FamilyMember,
  MemberProfile,
  PermissionGrant,
  StorageProviderType,
} from '../types';

// --- State shape ---

export interface SessionUser {
  userId: string;
  name: string;
  email: string;
  role: 'admin' | 'member' | 'owner';
}

export interface SessionState {
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
  storage: {
    provider: StorageProviderType;
    status: string;
  };
}

const initialState: SessionState = {
  status: 'loading',
  user: null,
  profile: null,
  family: null,
  agents: {
    available: [],
    myConfigs: [],
    agentTypes: {},
  },
  permissions: [],
  conversations: {
    items: [],
    nextCursor: undefined,
    lastFetched: null,
  },
  storage: {
    provider: 'local',
    status: 'active',
  },
};

// --- Actions ---

type SessionAction =
  | {
      type: 'SESSION_BOOTSTRAP';
      payload: {
        user: SessionUser;
        profile: MemberProfile | null;
        family: {info: Family; members: FamilyMember[]} | null;
        agents: {available: AvailableAgent[]; myConfigs: AgentConfig[]; agentTypes: Record<string, AgentTypeInfo>};
        permissions: PermissionGrant[];
        conversations: {items: Conversation[]; nextCursor?: string};
        storage?: {provider: StorageProviderType; status: string};
      };
    }
  | {type: 'SESSION_CLEAR'}
  | {type: 'UPDATE_STORAGE'; payload: {provider: StorageProviderType; status: string}}
  | {type: 'UPDATE_PROFILE'; payload: MemberProfile}
  | {type: 'UPDATE_FAMILY'; payload: {info: Family; members: FamilyMember[]} | null}
  | {type: 'UPDATE_AGENTS'; payload: {available: AvailableAgent[]; myConfigs: AgentConfig[]}}
  | {type: 'UPDATE_PERMISSIONS'; payload: PermissionGrant[]}
  | {
      type: 'SET_CONVERSATIONS';
      payload: {items: Conversation[]; nextCursor?: string};
    }
  | {type: 'ADD_CONVERSATION'; payload: Conversation}
  | {type: 'REMOVE_CONVERSATION'; payload: string};

// --- Reducer ---

function sessionReducer(state: SessionState, action: SessionAction): SessionState {
  switch (action.type) {
    case 'SESSION_BOOTSTRAP':
      return {
        status: 'authenticated',
        user: action.payload.user,
        profile: action.payload.profile,
        family: action.payload.family,
        agents: action.payload.agents,
        permissions: action.payload.permissions,
        conversations: {
          items: action.payload.conversations.items,
          nextCursor: action.payload.conversations.nextCursor,
          lastFetched: Date.now(),
        },
        storage: action.payload.storage ?? {provider: 'local', status: 'active'},
      };

    case 'SESSION_CLEAR':
      return {...initialState, status: 'unauthenticated'};

    case 'UPDATE_STORAGE':
      return {...state, storage: action.payload};

    case 'UPDATE_PROFILE':
      return {...state, profile: action.payload};

    case 'UPDATE_FAMILY':
      return {...state, family: action.payload};

    case 'UPDATE_AGENTS':
      return {...state, agents: {...state.agents, ...action.payload}};

    case 'UPDATE_PERMISSIONS':
      return {...state, permissions: action.payload};

    case 'SET_CONVERSATIONS':
      return {
        ...state,
        conversations: {
          items: action.payload.items,
          nextCursor: action.payload.nextCursor,
          lastFetched: Date.now(),
        },
      };

    case 'ADD_CONVERSATION':
      return {
        ...state,
        conversations: {
          ...state.conversations,
          items: [
            action.payload,
            ...state.conversations.items.filter(
              c => c.conversation_id !== action.payload.conversation_id,
            ),
          ],
        },
      };

    case 'REMOVE_CONVERSATION':
      return {
        ...state,
        conversations: {
          ...state.conversations,
          items: state.conversations.items.filter(
            c => c.conversation_id !== action.payload,
          ),
        },
      };

    default:
      return state;
  }
}

// --- Context ---

interface SessionContextValue {
  state: SessionState;
  dispatch: React.Dispatch<SessionAction>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({children}: {children: React.ReactNode}) {
  const [state, dispatch] = useReducer(sessionReducer, initialState);
  const value = useMemo(() => ({state, dispatch}), [state]);

  return (
    <SessionContext.Provider value={value}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSessionContext(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error('useSessionContext must be used within a SessionProvider');
  }
  return ctx;
}
