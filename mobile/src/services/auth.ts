import * as Keychain from 'react-native-keychain';

const TOKEN_KEY = 'homeagent_device_token';

export async function saveToken(token: string): Promise<void> {
  await Keychain.setGenericPassword(TOKEN_KEY, token, {
    service: TOKEN_KEY,
  });
}

export async function getToken(): Promise<string | null> {
  const credentials = await Keychain.getGenericPassword({service: TOKEN_KEY});
  if (credentials) {
    return credentials.password;
  }
  return null;
}

export async function clearToken(): Promise<void> {
  await Keychain.resetGenericPassword({service: TOKEN_KEY});
}
