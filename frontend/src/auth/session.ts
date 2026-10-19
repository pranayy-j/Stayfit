import {
  GoogleSignin,
  isErrorWithCode,
  isSuccessResponse,
  statusCodes,
} from '@react-native-google-signin/google-signin';
import { getCalendars } from 'expo-localization';
import * as SecureStore from 'expo-secure-store';

import { ApiError, getMe, loginWithGoogle, type User } from '../api/client';
import { GOOGLE_IOS_CLIENT_ID, GOOGLE_WEB_CLIENT_ID } from '../config';

const TOKEN_KEY = 'stayfit.accessToken';

GoogleSignin.configure({
  webClientId: GOOGLE_WEB_CLIENT_ID,
  iosClientId: GOOGLE_IOS_CLIENT_ID,
});

/** Returns the signed-in user, or null if there is no valid saved session. */
export async function restoreSession(): Promise<User | null> {
  const token = await SecureStore.getItemAsync(TOKEN_KEY);
  if (!token) return null;
  try {
    return await getMe(token);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      await SecureStore.deleteItemAsync(TOKEN_KEY);
    }
    return null;
  }
}

/** Runs the Google sign-in flow; returns null if the user cancelled. */
export async function signInWithGoogle(): Promise<User | null> {
  try {
    await GoogleSignin.hasPlayServices();
    const response = await GoogleSignin.signIn();
    if (!isSuccessResponse(response)) return null;

    const { idToken } = response.data;
    if (!idToken) throw new Error('Google did not return an ID token');

    const timezone = getCalendars()[0]?.timeZone ?? null;
    const { access_token, user } = await loginWithGoogle(idToken, timezone);
    await SecureStore.setItemAsync(TOKEN_KEY, access_token);
    return user;
  } catch (e) {
    if (isErrorWithCode(e) && e.code === statusCodes.IN_PROGRESS) return null;
    throw e;
  }
}

export async function signOut(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
  await GoogleSignin.signOut();
}
