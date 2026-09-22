import { MantineProvider } from '@mantine/core';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type {
  AiTestResult,
  Health,
  HistoryPage,
  Operation,
  ServiceSettings,
  Stats,
  SystemStatus,
} from '../types';

export function renderWithMantine(ui: ReactElement) {
  return render(<MantineProvider defaultColorScheme="dark">{ui}</MantineProvider>);
}

/** For a page rendered on its own, outside App's own BrowserRouter. */
export function renderRouted(ui: ReactElement, route = '/') {
  return renderWithMantine(<MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>);
}

export function someSettings(overrides: Partial<ServiceSettings> = {}): ServiceSettings {
  return {
    dedupe: 'language_codec',
    skip_image_subtitles: false,
    skip_undetermined_language: false,
    max_external_tracks: 24,
    sub_charset: null,
    mux_timeout_seconds: 14400,
    free_space_factor: 1.05,
    preserve_ownership: true,
    max_concurrent_muxes: 1,
    job_ttl_seconds: 3600,
    history_max_records: 200,
    ai_mode: 'off',
    ai_base_url: 'https://api.openai.com/v1',
    ai_model: '',
    ai_timeout_seconds: 30,
    ai_max_entries: 200,
    ai_api_key_set: false,
    log_level: 'INFO',
    locked: [],
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
    added_tracks: ['English (SRT)', 'Russian (AC3)'],
    rejected_tracks: [],
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
    health = { status: 'ok', version: '0.9.0', read_roots: ['/media'], auth_required: true },
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
    settings = someSettings(),
    aiTest = { ok: true, message: 'tiny replied', latency_ms: 120 },
  } = responses;

  const body = (path: string) => {
    if (path.startsWith('/healthz')) return health;
    if (path.startsWith('/v1/stats')) return stats;
    if (path.startsWith('/v1/system')) return system;
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
