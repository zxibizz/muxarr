import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { App } from './App';
import { renderWithProviders, stubFetch } from '../test/helpers';

describe('App', () => {
  it('renders the shell around the history it loads', async () => {
    stubFetch();
    renderWithProviders(<App />);

    expect(await screen.findByText('Show - S01E01')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /settings/i })).toBeInTheDocument();
    expect(await screen.findByText('Worker online')).toBeInTheDocument();
  });

  it('asks for a token when the daemon answers 401, and retries once given one', async () => {
    const fetchStub = stubFetch({ status: 401 });
    renderWithProviders(<App />);

    expect(await screen.findByText('API token required')).toBeInTheDocument();

    fetchStub.mockClear();
    stubFetch();
    await userEvent.type(screen.getByLabelText(/^token/i), 's3cret');
    await userEvent.click(screen.getByRole('button', { name: /connect/i }));

    expect(await screen.findByText('Show - S01E01')).toBeInTheDocument();
    expect(window.localStorage.getItem('muxarr.token')).toBe('s3cret');
  });

  it('surfaces a daemon that cannot be reached', async () => {
    stubFetch({ status: 503 });
    renderWithProviders(<App />);

    await waitFor(() => {
      expect(screen.getByText(/could not load history/i)).toBeInTheDocument();
    });
  });

  it('warns on every page when the worker is offline', async () => {
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
      },
    });
    renderWithProviders(<App />);

    expect(await screen.findByText('The worker is offline')).toBeInTheDocument();
    expect(screen.getByText('Worker offline')).toBeInTheDocument();
  });
});
