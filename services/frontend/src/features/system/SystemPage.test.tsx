import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderRouted, stubFetch } from '../../test/helpers';
import { SystemPage } from './SystemPage';

describe('SystemPage', () => {
  it('shows the worker and the queue it is working through', async () => {
    stubFetch({
      system: {
        version: '0.9.0',
        worker: {
          alive: true,
          last_seen_at: new Date().toISOString(),
          stale_after_seconds: 30,
          max_concurrent_muxes: 2,
        },
        queue: { pending: 3, running: 1, succeeded: 7, failed: 0 },
        health: [],
      },
    });
    renderRouted(<SystemPage />, '/system');

    expect(await screen.findByText('running')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(await screen.findByText('/media')).toBeInTheDocument();
    expect(screen.getByText('No problems found.')).toBeInTheDocument();
  });

  it('lists what the health checks found', async () => {
    stubFetch({
      system: {
        version: '0.9.0',
        worker: {
          alive: true,
          last_seen_at: new Date().toISOString(),
          stale_after_seconds: 30,
          max_concurrent_muxes: 1,
        },
        queue: { pending: 0, running: 0, succeeded: 0, failed: 0 },
        health: [
          { level: 'error', code: 'read_root_missing', message: 'Read root /media is missing' },
        ],
      },
    });
    renderRouted(<SystemPage />, '/system');

    expect(await screen.findByText('Read root /media is missing')).toBeInTheDocument();
    expect(screen.queryByText('No problems found.')).not.toBeInTheDocument();
  });

  it('explains what an offline worker means', async () => {
    stubFetch({
      system: {
        version: '0.9.0',
        worker: {
          alive: false,
          last_seen_at: null,
          stale_after_seconds: 30,
          max_concurrent_muxes: 1,
        },
        queue: { pending: 2, running: 0, succeeded: 0, failed: 0 },
        health: [{ level: 'error', code: 'worker_offline', message: 'The worker is offline' }],
      },
    });
    renderRouted(<SystemPage />, '/system');

    expect(await screen.findByText('Nothing is muxing')).toBeInTheDocument();
    expect(screen.getByText('never')).toBeInTheDocument();
  });
});
