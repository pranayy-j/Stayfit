export type GoogleSignInButtonProps = {
  /** True while the ID token is being exchanged with our backend. */
  busy: boolean;
  onIdToken: (idToken: string) => void;
  onError: (message: string) => void;
};
