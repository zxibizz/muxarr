import type {
  AiTestRequest,
  AiTestResult,
  Health,
  HistoryFilters,
  HistoryPage,
  Job,
  JobPage,
  JobState,
  Operation,
  ServiceSettings,
  SettingsPatch,
  Stats,
  SystemStatus,
} from './types';

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

async function request<T>(path: string, init: RequestInit = {}, body?: unknown): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  if (body !== undefined) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
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
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') {
      return body.detail;
    }
    // FastAPI's own validation errors are a list of objects, not a string.
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((item) => (item as { msg?: string }).msg ?? String(item))
        .join('; ');
    }
  } catch {
    // Not JSON; fall through to the status text.
  }
  return `${response.status} ${response.statusText}`;
}

export const api = {
  health: () => request<Health>('/healthz'),

  system: () => request<SystemStatus>('/v1/system'),

  stats: () => request<Stats>('/v1/stats'),

  history: (filters: HistoryFilters, limit: number, offset: number) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (filters.status) params.set('move_status', filters.status);
    if (filters.app) params.set('app', filters.app);
    if (filters.query.trim()) params.set('q', filters.query.trim());
    return request<HistoryPage>(`/v1/history?${params.toString()}`);
  },

  operation: (id: number) => request<Operation>(`/v1/history/${id}`),

  jobs: (state?: JobState, limit = 20, offset = 0) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (state) params.set('state', state);
    return request<JobPage>(`/v1/jobs?${params.toString()}`);
  },

  job: (id: string) => request<Job>(`/v1/jobs/${encodeURIComponent(id)}/detail`),

  clearHistory: () => request<{ deleted: number }>('/v1/history', { method: 'DELETE' }),

  settings: () => request<ServiceSettings>('/v1/settings'),

  updateSettings: (patch: SettingsPatch) =>
    request<ServiceSettings>('/v1/settings', { method: 'PATCH' }, patch),

  testAi: (candidate: AiTestRequest) =>
    request<AiTestResult>('/v1/settings/ai/test', { method: 'POST' }, candidate),
};
