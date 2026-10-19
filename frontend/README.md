# StayFit Frontend

React Native app built with [Expo](https://docs.expo.dev/) (TypeScript), targeting iOS and Android.

## Develop

```bash
npm install
cp .env.example .env   # set EXPO_PUBLIC_API_URL and the Google client IDs
npx expo run:ios       # or: npx expo run:android
```

Google Sign-In uses native code, so the app **does not run in Expo Go** — use a local development
build (`npx expo run:ios|android`). After the first build,
`npm start` is enough for JS changes. Rebuild after changing `EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID`
(it's baked into the iOS URL scheme via `app.config.ts`).

### Web

```bash
npm run web            # http://localhost:8081
```

Web sign-in uses Google Identity Services (free, no extra package) with the web client ID. Add every
origin you serve from (e.g. `http://localhost:8081` and `http://localhost`) to the web client's
**Authorized JavaScript origins** in Google Cloud Console. On web the session token is kept in
`localStorage` (SecureStore is native-only).

When running on a device or Android emulator, `localhost` is not your machine — use your LAN IP
(or `http://10.0.2.2:8000` on the Android emulator).

## Checks

```bash
npm run typecheck
npx expo-doctor
```

