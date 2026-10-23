import type { Tokens } from '../api/client';

// Web keeps no tokens in JavaScript: the API sets them as httpOnly cookies, which page scripts
// can't read, and the browser sends them itself.
export const tokenStore = {
  get: async (): Promise<Tokens | null> => null,
  set: async (_tokens: Tokens): Promise<void> => {},
  clear: async (): Promise<void> => {},
};
