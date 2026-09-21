import type { Health, HistoryFilters, HistoryPage, Operation, Stats } from './types';

const TOKEN_KEY = 'muxarr.token';

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }

  get unauthorised(): boolean {
    return this.status === 401;
  }
}

export function getToken(): string {
  return window.localStorage.getItem(TOKEN_KEY) ?? '';
}

export function setToken(token: string): void {
  if (token) {
    window.localStorage.setItem(TOKEN_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch (cause) {
    throw new ApiError(0, `cannot reach the muxarr daemon (${String(cause)})`);
  }

  if (!response.ok) {
    throw new ApiError(response.status, await describe(response));
  }
  return (await response.json()) as T;
}

async function describe(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    if (body.detail) {
      return body.detail;
    }
  } catch {
    // Not JSON; fall through to the status text.
  }
  return `${response.status} ${response.statusText}`;
}

export const api = {
  health: () => request<Health>('/healthz'),

  stats: () => request<Stats>('/v1/stats'),

  history: (filters: HistoryFilters, limit: number, offset: number) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (filters.status) params.set('move_status', filters.status);
    if (filters.app) params.set('app', filters.app);
    if (filters.query.trim()) params.set('q', filters.query.trim());
    return request<HistoryPage>(`/v1/history?${params.toString()}`);
  },

  operation: (id: number) => request<Operation>(`/v1/history/${id}`),

  clearHistory: () => request<{ deleted: number }>('/v1/history', { method: 'DELETE' }),
};
