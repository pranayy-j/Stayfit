import { getCalendars } from 'expo-localization';
import { Platform } from 'react-native';

import { getMe, loginWithGoogle, logout, type User } from '../api/client';
import { signOutOfGoogle } from './google';
import { tokenStore } from './tokenStore';

/** Returns the signed-in user, or null if there is no valid session. */
export async function restoreSession(): Promise<User | null> {
  // Native with nothing saved: signed out, no need to ask the API. Web can't tell (its
  // tokens are httpOnly cookies), so it always asks.
  if (Platform.OS !== 'web' && !(await tokenStore.get())) return null;
  try {
    // Refreshes the access token first if it has expired.
    return await getMe();
  } catch {
    // Session gone (the failed refresh already cleared saved tokens), or the API is unreachable.
    return null;
  }
}

/** Exchanges a Google ID token for a StayFit session. */
export async function signInWithGoogleIdToken(idToken: string): Promise<User> {
  const timezone = getCalendars()[0]?.timeZone ?? null;
  const { tokens, user } = await loginWithGoogle(idToken, timezone);
  // Native gets tokens to save; web gets httpOnly cookies instead (tokens is null).
  if (tokens) await tokenStore.set(tokens);
  return user;
}

export async function signOut(): Promise<void> {
  const stored = await tokenStore.get();
  try {
    await logout(stored?.refresh_token);
  } catch {
    // Still sign out on this device if the API can't be reached.
  }
  await tokenStore.clear();
  await signOutOfGoogle();
}
