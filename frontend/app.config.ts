import type { ConfigContext, ExpoConfig } from 'expo/config';

// iOS needs the *reversed* iOS client ID registered as a URL scheme for the Google redirect.
// e.g. 1234-abc.apps.googleusercontent.com -> com.googleusercontent.apps.1234-abc
const iosClientId = process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID;
const iosUrlScheme = iosClientId
  ? `com.googleusercontent.apps.${iosClientId.replace('.apps.googleusercontent.com', '')}`
  : undefined;

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...(config as ExpoConfig),
  plugins: [
    ...(config.plugins ?? []),
    ...(iosUrlScheme
      ? [['@react-native-google-signin/google-signin', { iosUrlScheme }] as [string, object]]
      : []),
  ],
});
