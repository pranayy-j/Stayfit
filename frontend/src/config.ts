// EXPO_PUBLIC_* vars are inlined at build time. Set per environment in .env or eas.json.
export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';
