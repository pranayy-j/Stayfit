import { Platform } from 'react-native';

import { tokenStore } from '../auth/tokenStore';
import { API_URL } from '../config';

const IS_WEB = Platform.OS === 'web';

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

function send(method: string, path: string, body?: unknown, accessToken?: string) {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  // Web: auth rides in httpOnly cookies, and this header tells the API to use them. Other sites
  // can't add it without passing CORS, so it also guards against cross-site requests.
  if (IS_WEB) headers['X-Client'] = 'web';
  else if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  return fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: IS_WEB ? 'include' : undefined,
  });
}

let refreshing: Promise<boolean> | undefined;

/** Gets new tokens with the refresh token. Concurrent callers share one request. */
function refreshSession(): Promise<boolean> {
  refreshing ??= doRefresh().finally(() => {
    refreshing = undefined;
  });
  return refreshing;
}

async function doRefresh(): Promise<boolean> {
  const stored = await tokenStore.get();
  if (!IS_WEB && !stored) return false;

  const res = await send(
    'POST',
    '/auth/refresh',
    stored ? { refresh_token: stored.refresh_token } : undefined,
  );
  if (res.status === 401) {
    await tokenStore.clear();
    return false;
  }
  if (!res.ok) throw new ApiError(`POST /auth/refresh failed with ${res.status}`, res.status);

  const { tokens } = (await res.json()) as RefreshResponse;
  if (tokens) await tokenStore.set(tokens);
  return true;
}

type RequestOptions = {
  body?: unknown;
  /** Send the user's credentials, and refresh them once if the API says they've expired. */
  auth?: boolean;
};

async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const { body, auth = false } = options;
  const accessToken = async () => (auth ? (await tokenStore.get())?.access_token : undefined);

  let res = await send(method, path, body, await accessToken());
  if (res.status === 401 && auth) {
    const refreshed = await refreshSession();
    // On web, another tab may have just refreshed the shared cookies, so retry either way.
    if (refreshed || IS_WEB) res = await send(method, path, body, await accessToken());
  }
  if (!res.ok) {
    throw new ApiError(`${method} ${path} failed with ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

export type User = {
  id: string;
  name: string;
  email: string;
  timezone: string;
  created_at: string;
};

export type Tokens = {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  /** Seconds until the access token expires. */
  expires_in: number;
};

export type LoginResponse = {
  /** Native only. null on web, where the tokens are httpOnly cookies. */
  tokens: Tokens | null;
  user: User;
  is_new_user: boolean;
};

type RefreshResponse = { tokens: Tokens | null };

export const loginWithGoogle = (idToken: string, timezone: string | null) =>
  request<LoginResponse>('POST', '/auth/google', { body: { id_token: idToken, timezone } });

export const getMe = () => request<User>('GET', '/auth/me', { auth: true });

/** Revokes the session on the server. Native passes its refresh token; web uses the cookie. */
export const logout = (refreshToken?: string) =>
  request<{ status: 'signed_out' }>('POST', '/auth/logout', {
    body: refreshToken ? { refresh_token: refreshToken } : undefined,
  });
