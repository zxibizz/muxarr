import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { App } from './App';
import { anAuthStatus, renderWithProviders, stubFetch } from '../test/helpers';

// App owns a BrowserRouter, and jsdom keeps the URL from one test to the next.
afterEach(() => window.history.replaceState(null, '', '/'));

describe('App', () => {
  it('renders the shell around the history it loads', async () => {
    stubFetch();
    renderWithProviders(<App />);

    expect(await screen.findByText('Show - S01E01')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /settings/i })).toBeInTheDocument();
    expect(await screen.findByText('Worker online')).toBeInTheDocument();
  });

  it('sends a signed-out browser to the login page, and back once signed in', async () => {
    const fetchStub = stubFetch({ auth: anAuthStatus({ authenticated: false, username: null }) });
    renderWithProviders(<App />);

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');

    await userEvent.type(screen.getByLabelText(/^username/i), 'admin');
    await userEvent.type(screen.getByLabelText(/^password/i), 'correct-horse');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText('Show - S01E01')).toBeInTheDocument();
    const login = fetchStub.mock.calls.find(([path]) => String(path) === '/v1/auth/login');
    expect(new Headers(login?.[1]?.headers).get('X-Requested-With')).toBe('XMLHttpRequest');
    expect(JSON.parse(String(login?.[1]?.body))).toEqual({
      username: 'admin',
      password: 'correct-horse',
    });
  });

  it('insists on creating a login on a fresh instance', async () => {
    stubFetch({
      auth: anAuthStatus({ setup_required: true, authenticated: false, username: null }),
    });
    renderWithProviders(<App />);

    expect(await screen.findByRole('heading', { name: 'Create a login' })).toBeInTheDocument();
    const create = screen.getByRole('button', { name: /create login/i });

    await userEvent.type(screen.getByLabelText(/^username/i), 'admin');
    await userEvent.type(screen.getByLabelText(/^password/i), 'short');
    expect(create).toBeDisabled();

    await userEvent.type(screen.getByLabelText(/^password/i), '-but-longer');
    await userEvent.type(screen.getByLabelText(/^confirm password/i), 'short-but-longer');
    await userEvent.click(create);

    expect(await screen.findByText('Show - S01E01')).toBeInTheDocument();
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
        health: [],
      },
    });
    renderWithProviders(<App />);

    expect(await screen.findByText('The worker is offline')).toBeInTheDocument();
    expect(screen.getByText('Worker offline')).toBeInTheDocument();
  });
});
