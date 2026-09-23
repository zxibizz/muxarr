import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderRouted, someSettings, stubFetch } from '../../test/helpers';
import { SettingsPage } from './SettingsPage';

async function loaded() {
  renderRouted(<SettingsPage />, '/settings');
  return screen.findByLabelText(/maximum external tracks/i);
}

function patchBody(fetchStub: ReturnType<typeof stubFetch>) {
  const patch = fetchStub.mock.calls.find(([, init]) => init?.method === 'PATCH');
  expect(patch).toBeDefined();
  return JSON.parse(String(patch?.[1]?.body)) as Record<string, unknown>;
}

async function editMaxTracks(value: string) {
  const tracks = screen.getByLabelText(/maximum external tracks/i);
  await userEvent.clear(tracks);
  await userEvent.type(tracks, value);
}

describe('SettingsPage', () => {
  it('shows the values the daemon reports', async () => {
    stubFetch({ settings: someSettings({ max_external_tracks: 7 }) });

    expect(await loaded()).toHaveValue('7');
  });

  it('only offers to save once something has changed', async () => {
    stubFetch();
    await loaded();

    expect(screen.queryByRole('button', { name: /save changes/i })).not.toBeInTheDocument();
    await editMaxTracks('3');
    expect(screen.getByRole('button', { name: /save changes/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /discard/i }));
    expect(screen.queryByRole('button', { name: /save changes/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/maximum external tracks/i)).toHaveValue('24');
  });

  it('saves an edited value', async () => {
    const fetchStub = stubFetch();
    await loaded();

    await editMaxTracks('3');
    await userEvent.click(screen.getByRole('button', { name: /save changes/i }));

    expect(await screen.findByText('Settings saved')).toBeInTheDocument();
    expect(patchBody(fetchStub)).toMatchObject({ max_external_tracks: 3 });
  });

  it('saves the keep lists as arrays', async () => {
    const fetchStub = stubFetch({ settings: someSettings({ keep_audio_languages: ['eng'] }) });
    await loaded();

    await userEvent.type(screen.getByLabelText(/keep subtitle languages/i), 'rus,');
    await userEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await screen.findByText('Settings saved');
    expect(patchBody(fetchStub)).toMatchObject({
      keep_audio_languages: ['eng'],
      keep_subtitle_languages: ['rus'],
    });
  });

  it('surfaces a daemon that refuses to hand the settings over', async () => {
    stubFetch({ statusByPath: { '/v1/settings': 422 } });
    renderRouted(<SettingsPage />, '/settings');

    await waitFor(() => {
      expect(screen.getByText(/could not load settings/i)).toBeInTheDocument();
    });
  });

  it('disables a field the environment pins and says which variable owns it', async () => {
    stubFetch({ settings: someSettings({ locked: ['dedupe'] }) });
    await loaded();

    expect(screen.getByLabelText(/duplicate handling/i)).toBeDisabled();
    expect(screen.getByText('MUXARR_DEDUPE')).toBeInTheDocument();
    expect(screen.getByText(/one setting is pinned/i)).toBeInTheDocument();
  });

  it('never sends a pinned field back', async () => {
    const fetchStub = stubFetch({ settings: someSettings({ locked: ['dedupe'] }) });
    await loaded();

    await editMaxTracks('3');
    await userEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await screen.findByText('Settings saved');
    expect(patchBody(fetchStub)).not.toHaveProperty('dedupe');
  });

  it('reports only whether a key is stored, never the key', async () => {
    stubFetch({ settings: someSettings({ ai_api_key_set: true }) });
    await loaded();

    expect(screen.getByLabelText(/^api key/i)).toHaveAttribute('placeholder', 'a key is stored');
  });

  it('pins the API key by its own variable', async () => {
    stubFetch({ settings: someSettings({ locked: ['ai_api_key'] }) });
    await loaded();

    expect(screen.getByLabelText(/^api key/i)).toBeDisabled();
    expect(document.getElementById('setting-ai_mode')).not.toBeDisabled();
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
});
