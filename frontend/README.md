# StayFit Frontend

React Native app built with [Expo](https://docs.expo.dev/) (TypeScript), targeting iOS and Android.

## Develop

```bash
npm install
cp .env.example .env   # point EXPO_PUBLIC_API_URL at your backend
npm start              # then press i (iOS simulator) / a (Android emulator), or scan with Expo Go
```

When running on a device or Android emulator, `localhost` is not your machine — use your LAN IP
(or `http://10.0.2.2:8000` on the Android emulator).

## Checks

```bash
npm run typecheck
npx expo-doctor
```

## Deploy

Builds and store submission go through [EAS](https://docs.expo.dev/eas/), configured in `eas.json`
(`development`, `preview`, `production` profiles; set the real API URLs there):

```bash
npm install -g eas-cli && eas login
eas build --platform all --profile production
eas submit --platform all --profile production
```
