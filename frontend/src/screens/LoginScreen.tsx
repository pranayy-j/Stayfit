import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { User } from '../api/client';
import { GoogleSignInButton } from '../auth/google';
import { signInWithGoogleIdToken } from '../auth/session';

type Props = { onSignedIn: (user: User) => void };

export default function LoginScreen({ onSignedIn }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleIdToken = async (idToken: string) => {
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await signInWithGoogleIdToken(idToken));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Sign-in failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>StayFit</Text>
      <GoogleSignInButton busy={busy} onIdToken={handleIdToken} onError={setError} />
      {error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignSelf: 'stretch',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  title: {
    fontSize: 32,
    fontWeight: '700',
    marginBottom: 48,
  },
  error: {
    color: '#d93025',
    marginTop: 16,
    textAlign: 'center',
  },
});
