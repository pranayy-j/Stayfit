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

export type User = {
  id: string;
  name: string;
  email: string;
  timezone: string;
  created_at: string;
};

export type LoginResponse = {
  access_token: string;
  user: User;
};

export const loginWithGoogle = (idToken: string, timezone: string | null) =>
  request<LoginResponse>('POST', '/auth/google', { id_token: idToken, timezone });

export const getMe = (token: string) => request<User>('GET', '/auth/me', undefined, token);
