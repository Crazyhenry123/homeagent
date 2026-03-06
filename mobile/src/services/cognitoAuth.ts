import * as SecureStore from 'expo-secure-store';
import {cognitoSignUp, cognitoConfirm, cognitoLogin, cognitoResendCode} from './api';
import type {LoginResponse, SignupResponse} from '../types';

const COGNITO_ACCESS_TOKEN_KEY = 'homeagent_cognito_access_token';
const COGNITO_ID_TOKEN_KEY = 'homeagent_cognito_id_token';
const COGNITO_REFRESH_TOKEN_KEY = 'homeagent_cognito_refresh_token';

export async function signUp(
  email: string,
  password: string,
  displayName: string,
): Promise<SignupResponse> {
  return cognitoSignUp({email, password, display_name: displayName});
}

export async function confirmSignUp(
  email: string,
  code: string,
): Promise<boolean> {
  const result = await cognitoConfirm({email, confirmation_code: code});
  return result.confirmed;
}

export async function signIn(
  email: string,
  password: string,
): Promise<LoginResponse> {
  const result = await cognitoLogin({email, password});

  // Store Cognito tokens in secure store
  await Promise.all([
    SecureStore.setItemAsync(COGNITO_ACCESS_TOKEN_KEY, result.tokens.access_token),
    SecureStore.setItemAsync(COGNITO_ID_TOKEN_KEY, result.tokens.id_token),
    SecureStore.setItemAsync(COGNITO_REFRESH_TOKEN_KEY, result.tokens.refresh_token),
  ]);

  return result;
}

export async function resendCode(email: string): Promise<boolean> {
  const result = await cognitoResendCode({email});
  return result.sent;
}

export async function getCognitoAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(COGNITO_ACCESS_TOKEN_KEY);
}

export async function getCognitoIdToken(): Promise<string | null> {
  return SecureStore.getItemAsync(COGNITO_ID_TOKEN_KEY);
}

export async function clearCognitoTokens(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(COGNITO_ACCESS_TOKEN_KEY),
    SecureStore.deleteItemAsync(COGNITO_ID_TOKEN_KEY),
    SecureStore.deleteItemAsync(COGNITO_REFRESH_TOKEN_KEY),
  ]);
}
