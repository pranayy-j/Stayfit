import * as SecureStore from 'expo-secure-store';

import type { Tokens } from '../api/client';

// Native (iOS/Android): tokens live in the Keychain / Keystore. The web build uses
// tokenStore.web.ts instead.
const KEY = 'stayfit.tokens';

export const tokenStore = {
  async get(): Promise<Tokens | null> {
    const raw = await SecureStore.getItemAsync(KEY);
    return raw ? (JSON.parse(raw) as Tokens) : null;
  },
  set: (tokens: Tokens) => SecureStore.setItemAsync(KEY, JSON.stringify(tokens)),
  clear: () => SecureStore.deleteItemAsync(KEY),
};
