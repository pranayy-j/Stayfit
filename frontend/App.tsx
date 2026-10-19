import { useEffect, useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { StyleSheet, Text, View } from 'react-native';

import { getHealth } from './src/api/client';
import { API_URL } from './src/config';

export default function App() {
  const [status, setStatus] = useState('checking…');

  useEffect(() => {
    getHealth()
      .then((h) => setStatus(h.status))
      .catch(() => setStatus('unreachable'));
  }, []);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>StayFit</Text>
      <Text>Backend ({API_URL}): {status}</Text>
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
});
