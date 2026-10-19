import { useEffect, useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { ActivityIndicator, Button, StyleSheet, Text, View } from 'react-native';

import type { User } from './src/api/client';
import { restoreSession, signOut } from './src/auth/session';
import LoginScreen from './src/screens/LoginScreen';

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [restoring, setRestoring] = useState(true);

  useEffect(() => {
    restoreSession()
      .then(setUser)
      .finally(() => setRestoring(false));
  }, []);

  const handleSignOut = async () => {
    await signOut();
    setUser(null);
  };

  return (
    <View style={styles.container}>
      {restoring ? (
        <ActivityIndicator />
      ) : user ? (
        <>
          <Text style={styles.title}>Hi, {user.name}</Text>
          <Text>{user.email}</Text>
          <Text style={styles.muted}>{user.timezone}</Text>
          <Button title="Sign out" onPress={handleSignOut} />
        </>
      ) : (
        <LoginScreen onSignedIn={setUser} />
      )}
      <StatusBar style="auto" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontSize: 24,
    fontWeight: '600',
    marginBottom: 8,
  },
  muted: {
    color: '#666',
    marginBottom: 24,
  },
});
