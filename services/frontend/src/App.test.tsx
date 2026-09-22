import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { App } from './App';
import { renderWithMantine, stubFetch } from './test/helpers';

describe('App', () => {
  it('renders the history it loads', async () => {
    stubFetch();
    renderWithMantine(<App />);

    expect(await screen.findByText('Show S01E01')).toBeInTheDocument();
    expect(screen.getByText('muxarr')).toBeInTheDocument();
  });

  it('asks for a token when the daemon answers 401, and retries once given one', async () => {
    const fetchStub = stubFetch({ status: 401 });
    renderWithMantine(<App />);

    expect(await screen.findByText('API token required')).toBeInTheDocument();

    fetchStub.mockClear();
    stubFetch();
    await userEvent.type(screen.getByLabelText(/^token/i), 's3cret');
    await userEvent.click(screen.getByRole('button', { name: /connect/i }));

    expect(await screen.findByText('Show S01E01')).toBeInTheDocument();
    expect(window.localStorage.getItem('muxarr.token')).toBe('s3cret');
  });

  it('surfaces a daemon that cannot be reached', async () => {
    stubFetch({ status: 503 });
    renderWithMantine(<App />);

    await waitFor(() => {
      expect(screen.getByText(/could not load history/i)).toBeInTheDocument();
    });
  });
});
