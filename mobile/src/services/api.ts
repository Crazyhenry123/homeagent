import Constants from 'expo-constants';
import {Platform} from 'react-native';
import type {
  ConversationListResponse,
  MessageListResponse,
  RegisterRequest,
  RegisterResponse,
} from '../types';
import {getToken} from './auth';

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
  const token = await getToken();
  const h: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    h['Authorization'] = `Bearer ${token}`;
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

export async function verify(): Promise<{
  valid: boolean;
  user_id: string;
  name: string;
}> {
  return request('/api/auth/verify', {method: 'POST'});
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
