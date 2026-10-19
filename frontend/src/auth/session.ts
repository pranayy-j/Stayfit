import { getCalendars } from 'expo-localization';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import { ApiError, getMe, loginWithGoogle, type User } from '../api/client';
import { signOutOfGoogle } from './google';

const TOKEN_KEY = 'stayfit.accessToken';

// expo-secure-store has no web implementation, so the web build keeps the token in localStorage.
const tokenStore =
  Platform.OS === 'web'
    ? {
        get: async () => localStorage.getItem(TOKEN_KEY),
        set: async (token: string) => localStorage.setItem(TOKEN_KEY, token),
        clear: async () => localStorage.removeItem(TOKEN_KEY),
      }
    : {
        get: () => SecureStore.getItemAsync(TOKEN_KEY),
        set: (token: string) => SecureStore.setItemAsync(TOKEN_KEY, token),
        clear: () => SecureStore.deleteItemAsync(TOKEN_KEY),
      };

/** Returns the signed-in user, or null if there is no valid saved session. */
export async function restoreSession(): Promise<User | null> {
  const token = await tokenStore.get();
  if (!token) return null;
  try {
    return await getMe(token);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      await tokenStore.clear();
    }
    return null;
  }
}

/** Exchanges a Google ID token for our own session token and saves it. */
export async function signInWithGoogleIdToken(idToken: string): Promise<User> {
  const timezone = getCalendars()[0]?.timeZone ?? null;
  const { access_token, user } = await loginWithGoogle(idToken, timezone);
  await tokenStore.set(access_token);
  return user;
}

export async function signOut(): Promise<void> {
  await tokenStore.clear();
  await signOutOfGoogle();
}
