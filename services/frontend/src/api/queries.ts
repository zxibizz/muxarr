import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { request } from './client';
import type {
  AiTestRequest,
  AiTestResult,
  ApiKey,
  AuthStatus,
  Credentials,
  CredentialsChange,
  Health,
  HistoryFilters,
  HistoryPage,
  Job,
  JobPage,
  ServiceSettings,
  SettingsPatch,
  Stats,
  SystemStatus,
  UserView,
} from './types';

export const HISTORY_PAGE_SIZE = 25;
// The newest jobs are the unfinished ones; anything older has a history row.
const JOB_WINDOW = 20;

const DASHBOARD_POLL_MS = 10_000;
const QUEUE_POLL_MS = 5_000;
// Fast enough to feel live, slow enough that a queue of watchers costs nothing.
const LIVE_JOB_POLL_MS = 2_000;

export const api = {
  health: () => request<Health>('/healthz'),
  system: () => request<SystemStatus>('/v1/system'),
  stats: () => request<Stats>('/v1/stats'),
  history: (filters: HistoryFilters, page: number) => {
    const params = new URLSearchParams({
      limit: String(HISTORY_PAGE_SIZE),
      offset: String((page - 1) * HISTORY_PAGE_SIZE),
    });
    if (filters.status) params.set('move_status', filters.status);
    if (filters.app) params.set('app', filters.app);
    if (filters.query.trim()) params.set('q', filters.query.trim());
    return request<HistoryPage>(`/v1/history?${params.toString()}`);
  },
  jobs: () => request<JobPage>(`/v1/jobs?limit=${JOB_WINDOW}&offset=0`),
  job: (id: string) => request<Job>(`/v1/jobs/${encodeURIComponent(id)}/detail`),
  clearHistory: () => request<{ deleted: number }>('/v1/history', { method: 'DELETE' }),
  settings: () => request<ServiceSettings>('/v1/settings'),
  updateSettings: (patch: SettingsPatch) =>
    request<ServiceSettings>('/v1/settings', { method: 'PATCH' }, patch),
  testAi: (candidate: AiTestRequest) =>
    request<AiTestResult>('/v1/settings/ai/test', { method: 'POST' }, candidate),
  authStatus: () => request<AuthStatus>('/v1/auth/status'),
  login: (credentials: Credentials) =>
    request<AuthStatus>('/v1/auth/login', { method: 'POST' }, credentials),
  setup: (credentials: Credentials) =>
    request<AuthStatus>('/v1/auth/setup', { method: 'POST' }, credentials),
  logout: () => request<undefined>('/v1/auth/logout', { method: 'POST' }),
  changeCredentials: (change: CredentialsChange) =>
    request<UserView>('/v1/auth/credentials', { method: 'PUT' }, change),
  apiKey: () => request<ApiKey>('/v1/settings/api-key'),
  regenerateApiKey: () => request<ApiKey>('/v1/settings/api-key/regenerate', { method: 'POST' }),
};

export const keys = {
  health: ['health'] as const,
  system: ['system'] as const,
  stats: ['stats'] as const,
  history: ['history'] as const,
  jobs: ['jobs'] as const,
  job: (id: string | null) => ['job', id] as const,
  settings: ['settings'] as const,
  auth: ['auth'] as const,
  apiKey: ['api-key'] as const,
};

export function useHealth() {
  return useQuery({ queryKey: keys.health, queryFn: api.health, staleTime: 60_000 });
}

export function useSystem() {
  return useQuery({
    queryKey: keys.system,
    queryFn: api.system,
    refetchInterval: DASHBOARD_POLL_MS,
  });
}

export function useStats() {
  return useQuery({
    queryKey: keys.stats,
    queryFn: api.stats,
    refetchInterval: DASHBOARD_POLL_MS,
  });
}

export function useHistory(filters: HistoryFilters, page: number) {
  return useQuery({
    queryKey: [...keys.history, filters, page],
    queryFn: () => api.history(filters, page),
    placeholderData: keepPreviousData,
    refetchInterval: DASHBOARD_POLL_MS,
  });
}

/** Jobs that have not produced a history entry yet. */
export function useUnsettledJobs() {
  return useQuery({
    queryKey: keys.jobs,
    queryFn: api.jobs,
    select: (page) => page.items.filter((job) => job.state !== 'succeeded'),
    refetchInterval: QUEUE_POLL_MS,
  });
}

export function isTerminal(job: Job | undefined): boolean {
  return job?.state === 'succeeded' || job?.state === 'failed';
}

export function useJob(id: string | null) {
  return useQuery({
    queryKey: keys.job(id),
    queryFn: () => api.job(id as string),
    enabled: id !== null,
    refetchInterval: (query) => (isTerminal(query.state.data) ? false : LIVE_JOB_POLL_MS),
  });
}

export function useClearHistory() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.clearHistory,
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.history }),
        client.invalidateQueries({ queryKey: keys.stats }),
      ]),
  });
}

export function useSettings() {
  // Never refetched behind the user's back: it would clobber a half-edited form.
  return useQuery({ queryKey: keys.settings, queryFn: api.settings, staleTime: Infinity });
}

export function useUpdateSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.updateSettings,
    onSuccess: (updated) => client.setQueryData(keys.settings, updated),
  });
}

export function useTestAi() {
  return useMutation({ mutationFn: api.testAi });
}

export function useAuthStatus() {
  return useQuery({
    queryKey: keys.auth,
    queryFn: api.authStatus,
    staleTime: 60_000,
    // Otherwise every component mounting after a failure resets it to pending,
    // and AuthGate swaps the whole app for a loader in a loop.
    retryOnMount: false,
  });
}

/** Signing in or out changes what every other query may see, so all of them start over. */
function useSignedInAs() {
  const client = useQueryClient();
  return (status: AuthStatus) => {
    client.setQueryData(keys.auth, status);
    void client.invalidateQueries({ predicate: (query) => query.queryKey[0] !== keys.auth[0] });
  };
}

export function useLogin() {
  const adopt = useSignedInAs();
  return useMutation({ mutationFn: api.login, onSuccess: adopt });
}

export function useSetup() {
  const adopt = useSignedInAs();
  return useMutation({ mutationFn: api.setup, onSuccess: adopt });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.logout,
    onSuccess: async () => {
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== keys.auth[0] });
      await client.invalidateQueries({ queryKey: keys.auth });
    },
  });
}

export function useChangeCredentials() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.changeCredentials,
    onSuccess: () => client.invalidateQueries({ queryKey: keys.auth }),
  });
}

export function useApiKey() {
  return useQuery({ queryKey: keys.apiKey, queryFn: api.apiKey, staleTime: Infinity });
}

export function useRegenerateApiKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.regenerateApiKey,
    onSuccess: (updated) => client.setQueryData(keys.apiKey, updated),
  });
}
