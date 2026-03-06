import * as SecureStore from 'expo-secure-store';

const TOKEN_KEY = 'homeagent_device_token';

export async function saveToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(TOKEN_KEY, token);
}

export async function getToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}

export async function clearToken(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
  // Also clear Cognito tokens if present
  try {
    const {clearCognitoTokens} = await import('./cognitoAuth');
    await clearCognitoTokens();
  } catch {
    // cognitoAuth module not available, ignore
  }
}
