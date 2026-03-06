import Constants from 'expo-constants';
import {Platform} from 'react-native';
import type {
  AgentConfig,
  AgentConfigsResponse,
  AgentTemplate,
  AgentTemplatesResponse,
  AgentTypesResponse,
  AvailableAgentsResponse,
  ConfirmRequest,
  ConfirmResponse,
  ConversationListResponse,
  Family,
  FamilyInvite,
  FamilyMember,
  FamilyRelationship,
  FamilyRelationshipsResponse,
  LoginRequest,
  LoginResponse,
  MemberProfile,
  MessageListResponse,
  PermissionGrant,
  PermissionsResponse,
  ProfileListResponse,
  RegisterRequest,
  RegisterResponse,
  RelationshipType,
  RequiredPermissionsResponse,
  ResendCodeRequest,
  ResendCodeResponse,
  SignupRequest,
  SignupResponse,
} from '../types';
import {getToken} from './auth';
import {emitAuthExpired} from './authEvents';

function getBaseUrl(): string {
  // Use configured URL from app.json extra if provided
  const configUrl = Constants.expoConfig?.extra?.apiBaseUrl;
  if (configUrl) {
    return configUrl;
  }

  // In development, auto-discover the dev machine's IP from Expo
  if (__DEV__) {
    const hostUri = Constants.expoConfig?.hostUri;
    if (hostUri) {
      const host = hostUri.split(':')[0];
      return `http://${host}:5000`;
    }
    return Platform.OS === 'android'
      ? 'http://10.0.2.2:5000'
      : 'http://localhost:5000';
  }

  return 'https://api.example.com';
}

export const BASE_URL = getBaseUrl();

async function headers(): Promise<Record<string, string>> {
  // Prefer Cognito access token over device token
  let authToken: string | null = null;
  try {
    const {getCognitoAccessToken} = await import('./cognitoAuth');
    authToken = await getCognitoAccessToken();
  } catch {
    // cognitoAuth module not available, fall through
  }

  if (!authToken) {
    authToken = await getToken();
  }

  const h: Record<string, string> = {
    'Content-Type': 'application/json',
    'bypass-tunnel-reminder': 'true',
  };
  if (authToken) {
    h['Authorization'] = `Bearer ${authToken}`;
  }
  return h;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const h = await headers();
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {...h, ...options.headers},
  });

  if (!response.ok) {
    if (response.status === 401) {
      emitAuthExpired();
    }
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

async function publicRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {'Content-Type': 'application/json', 'bypass-tunnel-reminder': 'true', ...options.headers},
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function register(
  data: RegisterRequest,
): Promise<RegisterResponse> {
  return request<RegisterResponse>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// --- Cognito Auth APIs ---

export async function cognitoSignUp(
  data: SignupRequest,
): Promise<SignupResponse> {
  return publicRequest<SignupResponse>('/api/auth/signup', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function cognitoConfirm(
  data: ConfirmRequest,
): Promise<ConfirmResponse> {
  return publicRequest<ConfirmResponse>('/api/auth/confirm', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function cognitoLogin(
  data: LoginRequest,
): Promise<LoginResponse> {
  return publicRequest<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function cognitoResendCode(
  data: ResendCodeRequest,
): Promise<ResendCodeResponse> {
  return publicRequest<ResendCodeResponse>('/api/auth/resend-code', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function verify(): Promise<{
  valid: boolean;
  user_id: string;
  name: string;
  role: string;
}> {
  return request('/api/auth/verify', {method: 'POST'});
}

export async function generateInviteCode(): Promise<{code: string}> {
  return request('/api/admin/invite-codes', {method: 'POST'});
}

export async function getConversations(
  limit = 20,
  cursor?: string,
): Promise<ConversationListResponse> {
  const params = new URLSearchParams({limit: String(limit)});
  if (cursor) {
    params.set('cursor', cursor);
  }
  return request(`/api/conversations?${params}`);
}

export async function getMessages(
  conversationId: string,
  limit = 50,
  cursor?: string,
): Promise<MessageListResponse> {
  const params = new URLSearchParams({limit: String(limit)});
  if (cursor) {
    params.set('cursor', cursor);
  }
  return request(`/api/conversations/${conversationId}/messages?${params}`);
}

export async function deleteConversation(
  conversationId: string,
): Promise<void> {
  await request(`/api/conversations/${conversationId}`, {method: 'DELETE'});
}

// --- Profile APIs ---

export async function getMyProfile(): Promise<MemberProfile> {
  return request<MemberProfile>('/api/profiles/me');
}

export async function updateMyProfile(
  updates: Partial<
    Pick<
      MemberProfile,
      'display_name' | 'family_role' | 'preferences' | 'health_notes' | 'interests'
    >
  >,
): Promise<MemberProfile> {
  return request<MemberProfile>('/api/profiles/me', {
    method: 'PUT',
    body: JSON.stringify(updates),
  });
}

// --- Admin Profile APIs ---

export async function listProfiles(): Promise<ProfileListResponse> {
  return request<ProfileListResponse>('/api/admin/profiles');
}

export async function getProfile(
  userId: string,
): Promise<MemberProfile> {
  return request<MemberProfile>(`/api/admin/profiles/${userId}`);
}

export async function updateProfile(
  userId: string,
  updates: Partial<MemberProfile>,
): Promise<MemberProfile> {
  return request<MemberProfile>(`/api/admin/profiles/${userId}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  });
}

// --- Agent Config APIs ---

export async function getAgentTypes(): Promise<AgentTypesResponse> {
  return request<AgentTypesResponse>('/api/admin/agents/types');
}

export async function getAgentConfigs(
  userId: string,
): Promise<AgentConfigsResponse> {
  return request<AgentConfigsResponse>(`/api/admin/agents/${userId}`);
}

export async function putAgentConfig(
  userId: string,
  agentType: string,
  data: {enabled: boolean; config?: Record<string, unknown>},
): Promise<AgentConfig> {
  return request<AgentConfig>(`/api/admin/agents/${userId}/${agentType}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteAgentConfig(
  userId: string,
  agentType: string,
): Promise<void> {
  await request(`/api/admin/agents/${userId}/${agentType}`, {
    method: 'DELETE',
  });
}

// --- Agent Template APIs (Admin) ---

export async function listAgentTemplates(): Promise<AgentTemplatesResponse> {
  return request<AgentTemplatesResponse>('/api/admin/agent-templates');
}

export async function createAgentTemplate(data: {
  name: string;
  agent_type: string;
  description: string;
  system_prompt: string;
  default_config?: Record<string, unknown>;
  available_to?: 'all' | string[];
}): Promise<AgentTemplate> {
  return request<AgentTemplate>('/api/admin/agent-templates', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateAgentTemplate(
  templateId: string,
  data: Partial<Pick<AgentTemplate, 'name' | 'description' | 'system_prompt' | 'default_config' | 'available_to'>>,
): Promise<AgentTemplate> {
  return request<AgentTemplate>(`/api/admin/agent-templates/${templateId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteAgentTemplate(templateId: string): Promise<void> {
  await request(`/api/admin/agent-templates/${templateId}`, {
    method: 'DELETE',
  });
}

// --- Member Agent Self-Service APIs ---

export async function getAvailableAgents(): Promise<AvailableAgentsResponse> {
  return request<AvailableAgentsResponse>('/api/agents/available');
}

export async function getMyAgents(): Promise<AgentConfigsResponse> {
  return request<AgentConfigsResponse>('/api/agents/my');
}

export async function enableMyAgent(agentType: string): Promise<AgentConfig> {
  return request<AgentConfig>(`/api/agents/my/${agentType}`, {
    method: 'PUT',
  });
}

export async function disableMyAgent(agentType: string): Promise<void> {
  await request(`/api/agents/my/${agentType}`, {method: 'DELETE'});
}

// --- Permission APIs ---

export async function getMyPermissions(): Promise<PermissionsResponse> {
  return request<PermissionsResponse>('/api/permissions');
}

export async function grantPermission(
  permissionType: string,
  config: Record<string, unknown>,
): Promise<PermissionGrant> {
  return request<PermissionGrant>(`/api/permissions/${permissionType}`, {
    method: 'PUT',
    body: JSON.stringify({config}),
  });
}

export async function revokePermission(
  permissionType: string,
): Promise<void> {
  await request(`/api/permissions/${permissionType}`, {method: 'DELETE'});
}

export async function getRequiredPermissions(
  agentType: string,
): Promise<RequiredPermissionsResponse> {
  return request<RequiredPermissionsResponse>(
    `/api/permissions/agent-required/${agentType}`,
  );
}

// --- WebSocket URL builder ---

export async function buildVoiceWsUrl(
  conversationId: string | null,
): Promise<string> {
  let token: string | null = null;
  try {
    const {getCognitoAccessToken} = await import('./cognitoAuth');
    token = await getCognitoAccessToken();
  } catch {
    // cognitoAuth not available
  }
  if (!token) {
    token = await getToken();
  }
  const wsBase = BASE_URL.replace(/^http/, 'ws');
  let url = `${wsBase}/api/voice?token=${encodeURIComponent(token || '')}`;
  if (conversationId) {
    url += `&conversation_id=${encodeURIComponent(conversationId)}`;
  }
  return url;
}

// --- Chat Media APIs ---

export async function uploadChatImage(
  contentType: string,
  fileSize: number,
): Promise<{media_id: string; upload_url: string}> {
  return request('/api/chat/upload-image', {
    method: 'POST',
    body: JSON.stringify({content_type: contentType, file_size: fileSize}),
  });
}

// --- Admin Delete Member ---

export async function deleteMember(userId: string): Promise<void> {
  await request(`/api/admin/profiles/${userId}`, {method: 'DELETE'});
}

// --- Family Tree APIs ---

export async function getFamilyRelationships(): Promise<FamilyRelationshipsResponse> {
  return request<FamilyRelationshipsResponse>(
    '/api/admin/family/relationships',
  );
}

export async function getUserRelationships(
  userId: string,
): Promise<FamilyRelationshipsResponse> {
  return request<FamilyRelationshipsResponse>(
    `/api/admin/family/relationships/${userId}`,
  );
}

export async function createRelationship(
  userId: string,
  relatedUserId: string,
  relationshipType: RelationshipType,
): Promise<FamilyRelationship> {
  return request<FamilyRelationship>('/api/admin/family/relationships', {
    method: 'POST',
    body: JSON.stringify({
      user_id: userId,
      related_user_id: relatedUserId,
      relationship_type: relationshipType,
    }),
  });
}

export async function deleteRelationship(
  userId: string,
  relatedUserId: string,
): Promise<void> {
  await request(
    `/api/admin/family/relationships/${userId}/${relatedUserId}`,
    {method: 'DELETE'},
  );
}

// --- Family Management APIs ---

export async function createFamily(
  name: string,
): Promise<Family> {
  return request<Family>('/api/family', {
    method: 'POST',
    body: JSON.stringify({name}),
  });
}

export async function getFamily(): Promise<{
  family: Family;
  members: FamilyMember[];
}> {
  return request('/api/family');
}

export async function inviteMember(
  email: string,
): Promise<FamilyInvite & {email_sent: boolean; family_name: string}> {
  return request('/api/family/invite', {
    method: 'POST',
    body: JSON.stringify({email}),
  });
}

export async function getPendingInvites(): Promise<{
  invites: FamilyInvite[];
}> {
  return request('/api/family/invites');
}

export async function cancelInvite(code: string): Promise<void> {
  await request(`/api/family/invites/${code}`, {method: 'DELETE'});
}
