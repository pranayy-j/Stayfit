import { useEffect, useRef } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { GOOGLE_WEB_CLIENT_ID } from '../config';
import type { GoogleSignInButtonProps } from './googleTypes';

// Web sign-in via Google Identity Services (https://developers.google.com/identity/gsi/web).
// It renders Google's own button and hands us an ID token for the web client ID, which the
// backend already accepts. Your dev origin (e.g. http://localhost:8081) must be listed under
// "Authorized JavaScript origins" on the web client in Google Cloud Console.

type Gis = {
  accounts: {
    id: {
      initialize(config: {
        client_id: string;
        callback: (response: { credential: string }) => void;
      }): void;
      renderButton(parent: HTMLElement, options: Record<string, unknown>): void;
      disableAutoSelect(): void;
    };
  };
};

declare global {
  interface Window {
    google?: Gis;
  }
}

let gisLoading: Promise<Gis> | undefined;

function loadGis(): Promise<Gis> {
  gisLoading ??= new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.onload = () => resolve(window.google!);
    script.onerror = () => {
      gisLoading = undefined;
      reject(new Error('Could not load Google Sign-In'));
    };
    document.head.appendChild(script);
  });
  return gisLoading;
}

export function GoogleSignInButton({ busy, onIdToken, onError }: GoogleSignInButtonProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // GIS keeps the callback from initialize(); route it through a ref so it sees fresh props.
  const onIdTokenRef = useRef(onIdToken);
  onIdTokenRef.current = onIdToken;

  useEffect(() => {
    if (!GOOGLE_WEB_CLIENT_ID) {
      onError('EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID is not set');
      return;
    }
    let cancelled = false;
    loadGis()
      .then((gis) => {
        const container = containerRef.current;
        if (cancelled || !container) return;
        gis.accounts.id.initialize({
          client_id: GOOGLE_WEB_CLIENT_ID,
          callback: ({ credential }) => onIdTokenRef.current(credential),
        });
        gis.accounts.id.renderButton(container, {
          theme: 'filled_blue',
          size: 'large',
          text: 'continue_with',
          shape: 'rectangular',
          width: 320,
        });
      })
      .catch((e: Error) => onError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <View style={styles.wrapper}>
      <div ref={containerRef} style={busy ? { display: 'none' } : undefined} />
      {busy && <ActivityIndicator />}
    </View>
  );
}

export async function signOutOfGoogle(): Promise<void> {
  // Stops GIS from silently re-selecting the same account next time.
  window.google?.accounts.id.disableAutoSelect();
}

const styles = StyleSheet.create({
  wrapper: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
