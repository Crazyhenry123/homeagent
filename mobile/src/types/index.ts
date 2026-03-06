export interface User {
  user_id: string;
  name: string;
  role: 'admin' | 'member' | 'owner';
}

export interface CognitoTokens {
  id_token: string;
  access_token: string;
  refresh_token: string;
}

export interface SignupRequest {
  email: string;
  password: string;
  display_name: string;
}

export interface SignupResponse {
  user_id: string;
  email: string;
}

export interface ConfirmRequest {
  email: string;
  confirmation_code: string;
}

export interface ConfirmResponse {
  confirmed: boolean;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  tokens: CognitoTokens;
  user: {
    user_id: string;
    name: string;
    email: string;
    role: 'admin' | 'member' | 'owner';
  };
}

export interface ResendCodeRequest {
  email: string;
}

export interface ResendCodeResponse {
  sent: boolean;
}

export interface Conversation {
  conversation_id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface MediaInfo {
  media_id: string;
  content_type: string;
}

export interface Message {
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

export interface ChatMediaUpload {
  localId: string;
  uri: string;
  contentType: string;
  fileSize: number;
  mediaId?: string;
  status: 'pending' | 'uploading' | 'uploaded' | 'error';
}

export interface RegisterRequest {
  invite_code: string;
  device_name: string;
  platform: 'ios' | 'android';
  display_name: string;
}

export interface RegisterResponse {
  user_id: string;
  device_token: string;
}

export interface SSEEvent {
  type: 'text_delta' | 'message_done' | 'error';
  content?: string;
  conversation_id?: string;
  message_id?: string;
}

export interface VoiceEvent {
  type: 'audio_chunk' | 'transcript' | 'session_end' | 'error';
  data?: string;
  role?: string;
  content?: string;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  next_cursor?: string;
}

export interface MessageListResponse {
  messages: Message[];
  next_cursor?: string;
}

export interface MemberProfile {
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

export interface AgentConfig {
  user_id: string;
  agent_type: string;
  enabled: boolean;
  config: Record<string, unknown>;
  updated_at: string;
}

export interface AgentTypeInfo {
  name: string;
  description: string;
  default_config: Record<string, unknown>;
  implemented: boolean;
  required_permissions?: PermissionType[];
  is_default?: boolean;
}

export interface AgentTypesResponse {
  agent_types: Record<string, AgentTypeInfo>;
}

export interface AgentConfigsResponse {
  agent_configs: AgentConfig[];
}

export interface ProfileListResponse {
  profiles: MemberProfile[];
}

export type RelationshipType = 'parent_of' | 'child_of' | 'spouse_of' | 'sibling_of';

export interface FamilyRelationship {
  user_id: string;
  related_user_id: string;
  relationship_type: RelationshipType;
  user_name?: string;
  related_user_name?: string;
  created_at: string;
}

export interface FamilyRelationshipsResponse {
  relationships: FamilyRelationship[];
}

export interface AgentTemplate {
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

export interface AgentTemplatesResponse {
  templates: AgentTemplate[];
}

export interface AvailableAgent extends AgentTemplate {
  enabled: boolean;
}

export interface AvailableAgentsResponse {
  agents: AvailableAgent[];
}

// --- Permission Types ---

export type PermissionType =
  | 'email_access'
  | 'calendar_access'
  | 'health_data'
  | 'medical_records';

export interface EmailAccessConfig {
  email_address: string;
  provider: 'gmail' | 'outlook' | 'other';
}

export interface CalendarAccessConfig {
  calendar_id: string;
  provider: 'gmail' | 'outlook' | 'other';
}

export interface HealthDataConfig {
  consent_given: boolean;
  data_sources: string[];
}

export interface MedicalRecordsConfig {
  folder_path: string;
  s3_prefix: string;
}

export type PermissionConfig =
  | EmailAccessConfig
  | CalendarAccessConfig
  | HealthDataConfig
  | MedicalRecordsConfig;

export interface PermissionGrant {
  user_id: string;
  permission_type: PermissionType;
  config: Record<string, unknown>;
  granted_at: string;
  granted_by: string;
  status: 'active' | 'revoked';
}

export interface PermissionsResponse {
  permissions: PermissionGrant[];
}

export interface RequiredPermissionsResponse {
  agent_type: string;
  required_permissions: PermissionType[];
}

export interface Family {
  family_id: string;
  name: string;
  owner_user_id: string;
  created_at: string;
}

export interface FamilyMember {
  family_id: string;
  user_id: string;
  role: 'owner' | 'member';
  joined_at: string;
  name: string;
}

export interface SessionBootstrapResponse {
  user: {
    user_id: string;
    name: string;
    email: string;
    role: 'admin' | 'member' | 'owner';
  };
  profile: MemberProfile | null;
  family: {
    info: Family;
    members: FamilyMember[];
  } | null;
  agents: {
    available: AvailableAgent[];
    my_configs: AgentConfig[];
  };
  permissions: PermissionGrant[];
  conversations: {
    items: Conversation[];
    next_cursor?: string;
  };
}

export interface FamilyInvite {
  code: string;
  created_by: string;
  status: string;
  invited_email?: string;
  family_id?: string;
  invite_type: 'email' | 'code';
  expires_at: string;
  created_at?: string;
}
