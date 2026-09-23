import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { useAuthGate } from '../app/auth-context';
import { request } from './client';
import type {
  AiTestRequest,
  AiTestResult,
  Health,
  HistoryFilters,
  HistoryPage,
  Job,
  JobPage,
  ServiceSettings,
  SettingsPatch,
  Stats,
  SystemStatus,
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
};

const keys = {
  health: ['health'] as const,
  system: ['system'] as const,
  stats: ['stats'] as const,
  history: ['history'] as const,
  jobs: ['jobs'] as const,
  job: (id: string | null) => ['job', id] as const,
  settings: ['settings'] as const,
};

/** Polling pauses while the token prompt is up; every request would only 401. */
function usePollEvery(ms: number): number | false {
  const { needsToken } = useAuthGate();
  return needsToken ? false : ms;
}

export function useHealth() {
  return useQuery({ queryKey: keys.health, queryFn: api.health, staleTime: 60_000 });
}

export function useSystem() {
  return useQuery({
    queryKey: keys.system,
    queryFn: api.system,
    refetchInterval: usePollEvery(DASHBOARD_POLL_MS),
  });
}

export function useStats() {
  return useQuery({
    queryKey: keys.stats,
    queryFn: api.stats,
    refetchInterval: usePollEvery(DASHBOARD_POLL_MS),
  });
}

export function useHistory(filters: HistoryFilters, page: number) {
  return useQuery({
    queryKey: [...keys.history, filters, page],
    queryFn: () => api.history(filters, page),
    placeholderData: keepPreviousData,
    refetchInterval: usePollEvery(DASHBOARD_POLL_MS),
  });
}

/** Jobs that have not produced a history entry yet. */
export function useUnsettledJobs() {
  return useQuery({
    queryKey: keys.jobs,
    queryFn: api.jobs,
    select: (page) => page.items.filter((job) => job.state !== 'succeeded'),
    refetchInterval: usePollEvery(QUEUE_POLL_MS),
  });
}

export function isTerminal(job: Job | undefined): boolean {
  return job?.state === 'succeeded' || job?.state === 'failed';
}

export function useJob(id: string | null) {
  const poll = usePollEvery(LIVE_JOB_POLL_MS);
  return useQuery({
    queryKey: keys.job(id),
    queryFn: () => api.job(id as string),
    enabled: id !== null,
    refetchInterval: (query) => (isTerminal(query.state.data) ? false : poll),
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
