import { API_URL } from '../config';

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown, token?: string): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new ApiError(`${method} ${path} failed with ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

export const apiGet = <T>(path: string, token?: string) => request<T>('GET', path, undefined, token);
export const apiPost = <T>(path: string, body: unknown, token?: string) =>
  request<T>('POST', path, body, token);

export type Health = { status: string };

export const getHealth = () => apiGet<Health>('/health');

export type User = {
  id: string;
  name: string;
  email: string;
  timezone: string;
  created_at: string;
};

export type LoginResponse = {
  access_token: string;
  token_type: 'bearer';
  user: User;
  is_new_user: boolean;
};

export const loginWithGoogle = (idToken: string, timezone: string | null) =>
  apiPost<LoginResponse>('/auth/google', { id_token: idToken, timezone });

export const getMe = (token: string) => apiGet<User>('/auth/me', token);
// this is a test commit