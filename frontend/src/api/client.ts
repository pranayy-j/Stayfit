import { API_URL } from '../config';

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) {
    throw new Error(`GET ${path} failed with ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export type Health = { status: string };

export const getHealth = () => apiGet<Health>('/health');
