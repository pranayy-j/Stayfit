// EXPO_PUBLIC_* vars are inlined at build time. Set per environment in .env or eas.json.
export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';

// The web client ID is what Google puts in the ID token's audience; the backend verifies it.
export const GOOGLE_WEB_CLIENT_ID = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID;
export const GOOGLE_IOS_CLIENT_ID = process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID;
