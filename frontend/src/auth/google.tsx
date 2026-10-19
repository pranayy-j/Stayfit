import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';
import {
  GoogleSignin,
  isErrorWithCode,
  isSuccessResponse,
  statusCodes,
} from '@react-native-google-signin/google-signin';

import { GOOGLE_IOS_CLIENT_ID, GOOGLE_WEB_CLIENT_ID } from '../config';
import type { GoogleSignInButtonProps } from './googleTypes';

// Native (iOS/Android) sign-in. The web build uses google.web.tsx instead.
GoogleSignin.configure({
  webClientId: GOOGLE_WEB_CLIENT_ID,
  iosClientId: GOOGLE_IOS_CLIENT_ID,
});

export function GoogleSignInButton({ busy, onIdToken, onError }: GoogleSignInButtonProps) {
  const [signingIn, setSigningIn] = useState(false);
  const loading = busy || signingIn;

  const handlePress = async () => {
    setSigningIn(true);
    try {
      await GoogleSignin.hasPlayServices();
      const response = await GoogleSignin.signIn();
      if (!isSuccessResponse(response)) return; // cancelled

      const { idToken } = response.data;
      if (!idToken) throw new Error('Google did not return an ID token');
      onIdToken(idToken);
    } catch (e) {
      if (isErrorWithCode(e) && e.code === statusCodes.IN_PROGRESS) return;
      onError(e instanceof Error ? e.message : 'Google sign-in failed');
    } finally {
      setSigningIn(false);
    }
  };

  return (
    <Pressable style={styles.button} onPress={handlePress} disabled={loading}>
      {loading ? (
        <ActivityIndicator color="#fff" />
      ) : (
        <Text style={styles.buttonText}>Continue with Google</Text>
      )}
    </Pressable>
  );
}

export async function signOutOfGoogle(): Promise<void> {
  await GoogleSignin.signOut();
}

const styles = StyleSheet.create({
  button: {
    backgroundColor: '#1a73e8',
    paddingVertical: 14,
    borderRadius: 8,
    width: '100%',
    maxWidth: 320,
    alignItems: 'center',
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
