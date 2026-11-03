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
**Authorized JavaScript origins** in Google Cloud Console, and to the API's `CORS_ORIGINS`.

On web the app keeps no tokens in JavaScript: the API sets them as httpOnly cookies, and every
request carries `X-Client: web` so the API knows to use them. Native apps keep their access and
refresh tokens in SecureStore and refresh them automatically on a `401`
(see `src/api/client.ts`). Safari doesn't send `Secure` cookies to `http://localhost`, so set
`COOKIE_SECURE=false` in the backend's `.env` to sign in on web in Safari.

When running on a device or Android emulator, `localhost` is not your machine — use your LAN IP
(or `http://10.0.2.2:8000` on the Android emulator).

## Checks

```bash
npm run typecheck
npx expo-doctor
```

