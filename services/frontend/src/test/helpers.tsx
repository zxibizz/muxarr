import { MantineProvider } from '@mantine/core';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { vi } from 'vitest';
import type { Health, HistoryPage, Operation, Stats, SystemStatus } from '../types';

export function renderWithMantine(ui: ReactElement) {
  return render(<MantineProvider defaultColorScheme="dark">{ui}</MantineProvider>);
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
  status?: number;
}

/** Route fetch by path so the component under test exercises the real api.ts. */
export function stubFetch(responses: Responses = {}) {
  const {
    status = 200,
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
  } = responses;

  const body = (path: string) => {
    if (path.startsWith('/healthz')) return health;
    if (path.startsWith('/v1/stats')) return stats;
    if (path.startsWith('/v1/system')) return system;
    return history;
  };

  const stub = vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    return new Response(JSON.stringify(status === 200 ? body(path) : { detail: 'invalid token' }), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  });

  vi.stubGlobal('fetch', stub);
  return stub;
}
