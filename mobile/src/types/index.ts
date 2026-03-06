export interface User {
  user_id: string;
  name: string;
  role: 'admin' | 'member';
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
  role: 'admin' | 'member';
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
