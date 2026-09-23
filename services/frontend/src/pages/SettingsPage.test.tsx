import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { AuthGateProvider } from '../auth';
import { SettingsPage } from './SettingsPage';
import { renderRouted, someSettings, stubFetch } from '../test/helpers';

function renderPage() {
  return renderRouted(
    <AuthGateProvider>
      <SettingsPage />
    </AuthGateProvider>,
    '/settings',
  );
}

async function loaded() {
  renderPage();
  return screen.findByRole('button', { name: /save settings/i });
}

describe('SettingsPage', () => {
  it('shows the values the daemon reports', async () => {
    stubFetch({ settings: someSettings({ max_external_tracks: 7 }) });
    await loaded();

    expect(screen.getByLabelText(/maximum external tracks/i)).toHaveValue('7');
  });

  it('saves an edited value', async () => {
    const fetchStub = stubFetch();
    await loaded();

    const tracks = screen.getByLabelText(/maximum external tracks/i);
    await userEvent.clear(tracks);
    await userEvent.type(tracks, '3');
    await userEvent.click(screen.getByRole('button', { name: /save settings/i }));

    await screen.findByText(/saved/i);
    const patch = fetchStub.mock.calls.find(([, init]) => init?.method === 'PATCH');
    expect(patch).toBeDefined();
    expect(JSON.parse(String(patch?.[1]?.body))).toMatchObject({ max_external_tracks: 3 });
  });

  it('saves the keep lists as arrays', async () => {
    const fetchStub = stubFetch({
      settings: someSettings({ keep_audio_languages: ['eng'] }),
    });
    await loaded();

    const subtitles = screen.getByRole('textbox', { name: /^keep subtitle languages/i });
    await userEvent.type(subtitles, 'rus,');
    await userEvent.click(screen.getByRole('button', { name: /save settings/i }));

    await screen.findByText(/saved/i);
    const patch = fetchStub.mock.calls.find(([, init]) => init?.method === 'PATCH');
    expect(JSON.parse(String(patch?.[1]?.body))).toMatchObject({
      keep_audio_languages: ['eng'],
      keep_subtitle_languages: ['rus'],
    });
  });

  it('surfaces a rejected value instead of pretending it saved', async () => {
    stubFetch({ statusByPath: { '/v1/settings': 422 } });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/could not load settings/i)).toBeInTheDocument();
    });
  });

  it('disables a field the environment pins and says which variable owns it', async () => {
    stubFetch({ settings: someSettings({ locked: ['dedupe'] }) });
    await loaded();

    expect(screen.getByRole('textbox', { name: /duplicate handling/i })).toBeDisabled();
    expect(screen.getAllByText(/MUXARR_DEDUPE/).length).toBeGreaterThan(0);
  });

  it('never sends a pinned field back', async () => {
    const fetchStub = stubFetch({ settings: someSettings({ locked: ['dedupe'] }) });
    await loaded();

    await userEvent.click(screen.getByRole('button', { name: /save settings/i }));

    await screen.findByText(/saved/i);
    const patch = fetchStub.mock.calls.find(([, init]) => init?.method === 'PATCH');
    expect(JSON.parse(String(patch?.[1]?.body))).not.toHaveProperty('dedupe');
  });

  it('reports only whether a key is stored, never the key', async () => {
    stubFetch({ settings: someSettings({ ai_api_key_set: true }) });
    await loaded();

    expect(screen.getByLabelText(/^api key/i)).toHaveAttribute(
      'placeholder',
      'a key is stored',
    );
  });
});

describe('the AI provider test', () => {
  it('stays disabled until there is something to test', async () => {
    stubFetch();
    await loaded();

    expect(screen.getByRole('button', { name: /test provider/i })).toBeDisabled();
  });

  it('reports a reachable provider', async () => {
    stubFetch({
      settings: someSettings({ ai_mode: 'fallback', ai_model: 'tiny', ai_api_key_set: true }),
      aiTest: { ok: true, message: 'tiny replied', latency_ms: 42 },
    });
    await loaded();

    await userEvent.click(screen.getByRole('button', { name: /test provider/i }));

    const alert = await screen.findByText(/provider reachable/i);
    expect(within(alert.closest('[role="alert"]') ?? alert).getByText(/42 ms/)).toBeTruthy();
  });

  it('reports the provider error without failing the page', async () => {
    stubFetch({
      settings: someSettings({ ai_mode: 'fallback', ai_model: 'tiny', ai_api_key_set: true }),
      aiTest: { ok: false, message: 'returned HTTP 401: invalid api key', latency_ms: 30 },
    });
    await loaded();

    await userEvent.click(screen.getByRole('button', { name: /test provider/i }));

    expect(await screen.findByText(/provider test failed/i)).toBeInTheDocument();
    expect(screen.getByText(/invalid api key/i)).toBeInTheDocument();
  });

  it('sends the typed key rather than the stored one', async () => {
    const fetchStub = stubFetch({
      settings: someSettings({ ai_mode: 'fallback', ai_model: 'tiny' }),
    });
    await loaded();

    await userEvent.type(screen.getByLabelText(/^api key/i), 'sk-typed');
    await userEvent.click(screen.getByRole('button', { name: /test provider/i }));

    await screen.findByText(/provider reachable/i);
    const probe = fetchStub.mock.calls.find(([path]) =>
      String(path).startsWith('/v1/settings/ai/test'),
    );
    expect(JSON.parse(String(probe?.[1]?.body))).toMatchObject({ api_key: 'sk-typed' });
  });
});
