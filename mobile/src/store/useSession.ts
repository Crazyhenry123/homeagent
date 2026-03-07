import {useMemo, useCallback} from 'react';
import {useSessionContext} from './SessionContext';
import type {SessionState, SessionUser} from './SessionContext';
import type {Conversation, MemberProfile} from '../types';
import {
  getSession,
  getMyProfile,
  updateMyProfile,
  getFamily,
  getAvailableAgents,
  getMyAgents,
  getMyPermissions,
  getConversations,
  getStorageProviders,
} from '../services/api';
import {clearToken} from '../services/auth';

export interface UseSessionReturn {
  session: SessionState;
  actions: {
    bootstrap: () => Promise<void>;
    logout: () => Promise<void>;
    refreshProfile: () => Promise<void>;
    updateProfile: (
      updates: Partial<
        Pick<
          MemberProfile,
          'display_name' | 'family_role' | 'preferences' | 'health_notes' | 'interests'
        >
      >,
    ) => Promise<MemberProfile>;
    refreshFamily: () => Promise<void>;
    refreshAgents: () => Promise<void>;
    refreshPermissions: () => Promise<void>;
    refreshConversations: () => Promise<void>;
    refreshStorage: () => Promise<void>;
    addConversation: (conv: Conversation) => void;
    removeConversation: (id: string) => void;
  };
  isOwnerOrAdmin: boolean;
}

export function useSession(): UseSessionReturn {
  const {state, dispatch} = useSessionContext();

  const bootstrap = useCallback(async () => {
    try {
      // Single API call to load all session data
      const data = await getSession();

      dispatch({
        type: 'SESSION_BOOTSTRAP',
        payload: {
          user: {
            userId: data.user.user_id,
            name: data.user.name,
            email: data.user.email ?? '',
            role: data.user.role,
          },
          profile: data.profile,
          family: data.family
            ? {info: data.family.info, members: data.family.members}
            : null,
          agents: {
            available: data.agents.available,
            myConfigs: data.agents.my_configs,
            agentTypes: data.agents.agent_types ?? {},
          },
          permissions: data.permissions,
          conversations: {
            items: data.conversations.items,
            nextCursor: data.conversations.next_cursor,
          },
          storage: data.storage,
        },
      });
    } catch {
      // Session fetch failed — user is not authenticated
      dispatch({type: 'SESSION_CLEAR'});
    }
  }, [dispatch]);

  const logout = useCallback(async () => {
    await clearToken();
    try {
      const {clearCognitoTokens} = await import('../services/cognitoAuth');
      await clearCognitoTokens();
    } catch {
      // cognitoAuth module not available
    }
    dispatch({type: 'SESSION_CLEAR'});
  }, [dispatch]);

  const refreshProfile = useCallback(async () => {
    const profile = await getMyProfile();
    dispatch({type: 'UPDATE_PROFILE', payload: profile});
  }, [dispatch]);

  const updateProfile = useCallback(
    async (
      updates: Partial<
        Pick<
          MemberProfile,
          'display_name' | 'family_role' | 'preferences' | 'health_notes' | 'interests'
        >
      >,
    ): Promise<MemberProfile> => {
      const updated = await updateMyProfile(updates);
      dispatch({type: 'UPDATE_PROFILE', payload: updated});
      return updated;
    },
    [dispatch],
  );

  const refreshFamily = useCallback(async () => {
    try {
      const result = await getFamily();
      dispatch({
        type: 'UPDATE_FAMILY',
        payload: {info: result.family, members: result.members},
      });
    } catch {
      // Family may not exist (404 for members without a family)
      dispatch({type: 'UPDATE_FAMILY', payload: null});
    }
  }, [dispatch]);

  const refreshAgents = useCallback(async () => {
    const [availableResult, myResult] = await Promise.all([
      getAvailableAgents(),
      getMyAgents(),
    ]);

    dispatch({
      type: 'UPDATE_AGENTS',
      payload: {
        available: availableResult.agents,
        myConfigs: myResult.agent_configs,
      },
    });
  }, [dispatch]);

  const refreshPermissions = useCallback(async () => {
    const result = await getMyPermissions();
    dispatch({type: 'UPDATE_PERMISSIONS', payload: result.permissions});
  }, [dispatch]);

  const refreshStorage = useCallback(async () => {
    try {
      const result = await getStorageProviders();
      dispatch({
        type: 'UPDATE_STORAGE',
        payload: {
          provider: result.current_provider,
          status: result.current_status,
        },
      });
    } catch {
      // Storage info may not be available
    }
  }, [dispatch]);

  const refreshConversations = useCallback(async () => {
    const result = await getConversations();
    dispatch({
      type: 'SET_CONVERSATIONS',
      payload: {
        items: result.conversations,
        nextCursor: result.next_cursor,
      },
    });
  }, [dispatch]);

  const addConversation = useCallback(
    (conv: Conversation) => {
      dispatch({type: 'ADD_CONVERSATION', payload: conv});
    },
    [dispatch],
  );

  const removeConversation = useCallback(
    (id: string) => {
      dispatch({type: 'REMOVE_CONVERSATION', payload: id});
    },
    [dispatch],
  );

  const isOwnerOrAdmin = useMemo(() => {
    const role = state.user?.role;
    return role === 'owner' || role === 'admin';
  }, [state.user?.role]);

  const actions = useMemo(
    () => ({
      bootstrap,
      logout,
      refreshProfile,
      updateProfile,
      refreshFamily,
      refreshAgents,
      refreshPermissions,
      refreshConversations,
      refreshStorage,
      addConversation,
      removeConversation,
    }),
    [
      bootstrap,
      logout,
      refreshProfile,
      updateProfile,
      refreshFamily,
      refreshAgents,
      refreshPermissions,
      refreshConversations,
      refreshStorage,
      addConversation,
      removeConversation,
    ],
  );

  return {session: state, actions, isOwnerOrAdmin};
}
