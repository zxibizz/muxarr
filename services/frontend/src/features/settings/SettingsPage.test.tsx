import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { anAuthStatus, renderRouted, someSettings, stubFetch } from '../../test/helpers';
import { FIELDS, SECTIONS } from './fields';
import { SettingsPage } from './SettingsPage';

async function loaded(route = '/settings') {
  renderRouted(<SettingsPage />, route);
  return screen.findByLabelText(/maximum external tracks/i);
}

async function openSection(name: RegExp) {
  await userEvent.click(screen.getByRole('tab', { name }));
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
    await openSection(/^ai track discovery/i);

    expect(screen.getByLabelText(/^api key/i)).toHaveAttribute('placeholder', 'a key is stored');
  });

  it('pins the API key by its own variable', async () => {
    stubFetch({ settings: someSettings({ locked: ['ai_api_key'] }) });
    await loaded();
    await openSection(/^ai track discovery/i);

    expect(screen.getByLabelText(/^api key/i)).toBeDisabled();
    expect(document.getElementById('setting-ai_mode')).not.toBeDisabled();
  });
});

describe('the settings sections', () => {
  it('shows one section at a time', async () => {
    stubFetch();
    await loaded();
    const panel = () => within(screen.getByRole('tabpanel'));
    expect(panel().queryByLabelText(/mux timeout/i)).not.toBeInTheDocument();

    await openSection(/^muxing/i);

    expect(panel().getByLabelText(/mux timeout/i)).toBeVisible();
    expect(panel().queryByLabelText(/maximum external tracks/i)).not.toBeInTheDocument();
  });

  it('opens the section named in the URL', async () => {
    stubFetch();
    await loaded('/settings?section=ai');

    expect(screen.getByRole('tab', { name: /^ai track discovery/i })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('falls back to track selection for an unknown section', async () => {
    stubFetch();
    expect(await loaded('/settings?section=nope')).toBeVisible();
  });

  it('keeps an edit across a section switch and marks where it is', async () => {
    stubFetch();
    await loaded();

    await editMaxTracks('3');
    await openSection(/^muxing/i);

    expect(screen.getByRole('tab', { name: /^track selection.*unsaved changes/i })).toBeTruthy();
    expect(screen.getByRole('tab', { name: /^muxing$/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /save changes/i })).toBeInTheDocument();

    await openSection(/^track selection/i);
    expect(screen.getByLabelText(/maximum external tracks/i)).toHaveValue('3');
  });

  it('switches section from the burger menu', async () => {
    stubFetch();
    await loaded();

    await userEvent.click(screen.getByRole('button', { name: /settings sections/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /^muxing/i }));

    expect(screen.getByLabelText(/mux timeout/i)).toBeVisible();
  });

  it('places every setting in exactly one section', () => {
    const placed = SECTIONS.flatMap((section) => [...section.fields]);

    expect([...placed].sort()).toEqual([...FIELDS, 'ai_api_key'].sort());
  });
});

describe('the AI provider test', () => {
  it('stays disabled until there is something to test', async () => {
    stubFetch();
    await loaded();
    await openSection(/^ai track discovery/i);

    expect(screen.getByRole('button', { name: /test provider/i })).toBeDisabled();
  });

  it('reports a reachable provider', async () => {
    stubFetch({
      settings: someSettings({ ai_mode: 'fallback', ai_model: 'tiny', ai_api_key_set: true }),
      aiTest: { ok: true, message: 'tiny replied', latency_ms: 42 },
    });
    await loaded();
    await openSection(/^ai track discovery/i);

    await userEvent.click(screen.getByRole('button', { name: /test provider/i }));

    const alert = await screen.findByText(/provider reachable/i);
    expect(within(alert.closest('[role="alert"]') ?? alert).getByText(/42 ms/)).toBeTruthy();
  });
});

describe('the security section', () => {
  it('shows the API key and regenerates it only once confirmed', async () => {
    const fetchStub = stubFetch();
    await loaded('/settings?section=security');
    const regenerations = () =>
      fetchStub.mock.calls.filter(([path]) => String(path).endsWith('/api-key/regenerate'));

    expect(await screen.findByDisplayValue('0123456789abcdef0123456789abcdef')).toBeVisible();

    await userEvent.click(screen.getByRole('button', { name: /regenerate api key/i }));
    const dialog = await screen.findByRole('dialog');
    expect(regenerations()).toHaveLength(0);

    await userEvent.click(within(dialog).getByRole('button', { name: /^regenerate$/i }));

    expect(await screen.findByText('API key regenerated')).toBeInTheDocument();
    expect(regenerations()).toHaveLength(1);
  });

  it('offers no regeneration for a pinned key', async () => {
    stubFetch({ apiKey: { api_key: 'from-compose', locked: true } });
    await loaded('/settings?section=security');

    expect(await screen.findByDisplayValue('from-compose')).toBeVisible();
    expect(screen.queryByRole('button', { name: /regenerate api key/i })).not.toBeInTheDocument();
    expect(screen.getByText('MUXARR_API_KEY', { selector: 'code' })).toBeInTheDocument();
  });

  it('locks the login fields when the environment pins them', async () => {
    stubFetch({ auth: anAuthStatus({ credentials_locked: true }) });
    await loaded('/settings?section=security');

    expect(await screen.findByLabelText(/^username/i)).toBeDisabled();
    expect(screen.getByRole('button', { name: /^change$/i })).toBeDisabled();
  });

  it('shows the auth method but leaves choosing it to the environment', async () => {
    stubFetch({ auth: anAuthStatus({ method: 'external' }) });
    await loaded('/settings?section=security');

    const method = await screen.findByDisplayValue(/reverse proxy signs users in/i);
    expect(method).toHaveAttribute('readonly');
    expect(screen.getByText(/^Pinned by/)).toBeInTheDocument();
  });
});
