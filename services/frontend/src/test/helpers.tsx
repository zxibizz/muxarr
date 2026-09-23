import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router';
import { vi } from 'vitest';
import type {
  AddedTrack,
  AiTestResult,
  Health,
  HistoryPage,
  Job,
  JobPage,
  LogEntry,
  Operation,
  RejectedTrack,
  ServiceSettings,
  Stats,
  SystemStatus,
} from '../api/types';
import { AppProviders } from '../app/AppProviders';
import { theme } from '../app/theme';

/** Everything main.tsx provides except the router, so App can bring its own. */
export function renderWithProviders(ui: ReactElement) {
  return render(
    <MantineProvider theme={theme} forceColorScheme="dark" env="test">
      <Notifications />
      <AppProviders>{ui}</AppProviders>
    </MantineProvider>,
  );
}

/** For a page rendered on its own, outside App's BrowserRouter. */
export function renderRouted(ui: ReactElement, route = '/') {
  return renderWithProviders(<MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>);
}

export function aRejection(overrides: Partial<RejectedTrack> = {}): RejectedTrack {
  return {
    track: 'eng.srt',
    reason: 'already present in container',
    kind: 'subtitles',
    language: 'eng',
    source: 'heuristic',
    code: 'already_present',
    ...overrides,
  };
}

export function someSettings(overrides: Partial<ServiceSettings> = {}): ServiceSettings {
  return {
    dedupe: 'language_codec',
    skip_image_subtitles: false,
    skip_undetermined_language: false,
    max_external_tracks: 24,
    sub_charset: null,
    keep_audio_languages: [],
    keep_subtitle_languages: [],
    mux_timeout_seconds: 14400,
    free_space_factor: 1.05,
    preserve_ownership: true,
    max_concurrent_muxes: 1,
    job_ttl_seconds: 3600,
    history_max_records: 200,
    operation_log_max_entries: 500,
    ai_mode: 'off',
    ai_base_url: 'https://api.openai.com/v1',
    ai_model: '',
    ai_timeout_seconds: 30,
    ai_max_entries: 200,
    ai_name_tracks: false,
    ai_api_key_set: false,
    log_level: 'INFO',
    locked: [],
    ...overrides,
  };
}

export function aTrack(overrides: Partial<AddedTrack> = {}): AddedTrack {
  return {
    kind: 'subtitles',
    label: 'English',
    language: 'eng',
    name: 'English',
    forced: false,
    hearing_impaired: false,
    variant: null,
    file: 'English.srt',
    source: 'heuristic',
    ...overrides,
  };
}

export function aLogEntry(overrides: Partial<LogEntry> = {}): LogEntry {
  return {
    ts: '2026-09-22T10:00:00+00:00',
    level: 'INFO',
    component: 'usecase.import',
    message: 'embedding subtitles English',
    stage: 'selection',
    context: {},
    ...overrides,
  };
}

export function aJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 'job-1',
    state: 'running',
    result: null,
    error: null,
    history_id: null,
    app: 'sonarr',
    title: 'Show S01E02.mkv',
    source_path: '/downloads/Show.S01E02/Show.S01E02.mkv',
    destination_path: '/media/Show/Season 01/Show - S01E02.mkv',
    transfer_mode: 'Move',
    dry_run: false,
    created_at: '2026-09-22T10:00:00+00:00',
    updated_at: '2026-09-22T10:00:05+00:00',
    log: [aLogEntry()],
    ...overrides,
  };
}

export function anOperation(overrides: Partial<Operation> = {}): Operation {
  return {
    id: 1,
    created_at: '2026-09-22T10:00:00+00:00',
    app: 'sonarr',
    title: 'Show S01E01',
    move_status: 'RenameRequested',
    reason: 'embedded 2 external tracks',
    source_path: '/downloads/Show.S01E01/Show.S01E01.mkv',
    destination_path: '/media/Show/Season 01/Show - S01E01.mkv',
    media_file: '/media/Show/Season 01/Show - S01E01.mkv',
    transfer_mode: 'Move',
    season: 1,
    episodes: [1],
    added_tracks: [
      aTrack(),
      aTrack({ kind: 'audio', label: 'Russian', language: 'rus', file: 'rus.mka', source: 'ai' }),
    ],
    rejected_tracks: [],
    removed_tracks: [],
    log: [aLogEntry()],
    duration_ms: 12_000,
    source_bytes: 1024,
    output_bytes: 2048,
    dry_run: false,
    ...overrides,
  };
}

interface Responses {
  health?: Health;
  stats?: Stats;
  system?: SystemStatus;
  history?: HistoryPage;
  jobs?: JobPage;
  settings?: ServiceSettings;
  aiTest?: AiTestResult;
  status?: number;
  /** Per-route override, so one endpoint can fail while the rest succeed. */
  statusByPath?: Record<string, number>;
}

/** Route fetch by path so the component under test exercises the real api.ts. */
export function stubFetch(responses: Responses = {}) {
  const {
    status = 200,
    statusByPath = {},
    health = {
      status: 'ok',
      version: '0.9.0',
      read_roots: ['/media'],
      auth_required: true,
      worker_seen_at: '2026-09-22T10:00:00+00:00',
      worker_alive: true,
    },
    stats = { total: 1, muxed: 1, deferred: 0, tracks_added: 2, last_24h: 1 },
    system = {
      version: '0.9.0',
      worker: {
        alive: true,
        last_seen_at: '2026-09-22T10:00:00+00:00',
        stale_after_seconds: 30,
        max_concurrent_muxes: 1,
      },
      queue: { pending: 0, running: 0, succeeded: 1, failed: 0 },
    },
    history = { items: [anOperation()], total: 1, limit: 25, offset: 0 },
    jobs = { items: [], total: 0, limit: 20, offset: 0 },
    settings = someSettings(),
    aiTest = { ok: true, message: 'tiny replied', latency_ms: 120 },
  } = responses;

  const body = (path: string) => {
    if (path.startsWith('/healthz')) return health;
    if (path.startsWith('/v1/stats')) return stats;
    if (path.startsWith('/v1/system')) return system;
    // A single job, not the page: /v1/jobs/{id}/detail.
    if (path.startsWith('/v1/jobs/')) return jobs.items[0] ?? aJob();
    if (path.startsWith('/v1/jobs')) return jobs;
    if (path.startsWith('/v1/settings/ai/test')) return aiTest;
    if (path.startsWith('/v1/settings')) return settings;
    return history;
  };

  const statusFor = (path: string) => {
    const match = Object.keys(statusByPath).find((prefix) => path.startsWith(prefix));
    return match ? statusByPath[match] : status;
  };

  const stub = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const code = statusFor(path);
    if (code !== 200) {
      return json({ detail: code === 401 ? 'invalid token' : 'the daemon refused that' }, code);
    }
    // A PATCH echoes what it was sent, as the daemon does.
    if (path.startsWith('/v1/settings') && init?.method === 'PATCH') {
      const sent = JSON.parse(String(init.body)) as Partial<ServiceSettings>;
      return json({ ...settings, ...sent, ai_api_key: undefined }, 200);
    }
    return json(body(path), 200);
  });

  vi.stubGlobal('fetch', stub);
  return stub;
}

function json(payload: unknown, status: number) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
