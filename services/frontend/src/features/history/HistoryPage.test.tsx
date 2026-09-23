import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import {
  aJob,
  aLogEntry,
  aRejection,
  anOperation,
  renderRouted,
  stubFetch,
} from '../../test/helpers';
import { HistoryPage } from './HistoryPage';

function page(items = [anOperation()]) {
  return { items, total: items.length, limit: 25, offset: 0 };
}

async function openOperation(name = /open show - s01e01/i) {
  renderRouted(<HistoryPage />);
  await userEvent.click(await screen.findByRole('row', { name }));
  return screen.findByRole('dialog');
}

async function openTab(drawer: HTMLElement, name: RegExp) {
  await userEvent.click(within(drawer).getByRole('tab', { name }));
}

describe('HistoryPage', () => {
  it('names each track by kind and language, without an "[ai]" suffix', async () => {
    stubFetch();
    renderRouted(<HistoryPage />);

    expect(await screen.findByLabelText('audio: Russian')).toBeInTheDocument();
    expect(screen.getByLabelText('subtitles: English')).toBeInTheDocument();
    expect(screen.queryByText(/\[ai\]/i)).not.toBeInTheDocument();
  });

  it('leads with the name *arr gave the file and keeps the release name beneath it', async () => {
    stubFetch({
      history: page([anOperation({ title: 'Show.S01E01.1080p.WEB-DL-GRP.mkv' })]),
    });
    renderRouted(<HistoryPage />);

    expect(await screen.findByText('Show - S01E01')).toBeInTheDocument();
    expect(screen.getByText('Show.S01E01.1080p.WEB-DL-GRP.mkv')).toBeInTheDocument();
  });

  it('explains what happened when an operation is opened', async () => {
    stubFetch({
      history: page([
        anOperation({
          log: [
            aLogEntry({
              stage: 'probe',
              message: 'source already holds 1 audio track',
              context: { container: 'Matroska', skip_image_subtitles: 'False' },
            }),
          ],
        }),
      ]),
    });
    const drawer = await openOperation();

    await openTab(drawer, /what happened/i);
    expect(within(drawer).getAllByText('source already holds 1 audio track').length).toBeGreaterThan(0);
    // Python's str(False) is translated for humans.
    expect(within(drawer).getByText('no')).toBeInTheDocument();

    await openTab(drawer, /tracks/i);
    expect(within(drawer).getByText('by AI')).toBeInTheDocument();
    expect(within(drawer).getByText('by filename')).toBeInTheDocument();
  });

  it('labels a passed-over sidecar by why it was skipped', async () => {
    stubFetch({ history: page([anOperation({ rejected_tracks: [aRejection()] })]) });
    const drawer = await openOperation();

    await openTab(drawer, /tracks/i);
    expect(within(drawer).getByText('Sidecars passed over')).toBeInTheDocument();
    expect(within(drawer).getByText('Already in file')).toBeInTheDocument();
  });

  it('lists the source tracks the keep lists stripped', async () => {
    stubFetch({
      history: page([
        anOperation({
          removed_tracks: [
            {
              index: 2,
              kind: 'audio',
              language: 'fre',
              name: 'French',
              codec: 'ac3',
              forced: false,
              reason: 'language is not in the keep list',
            },
          ],
        }),
      ]),
    });
    const drawer = await openOperation();

    await openTab(drawer, /tracks/i);
    expect(within(drawer).getByText('Removed from source')).toBeInTheDocument();
    expect(within(drawer).getByText(/track 2, language is not in the keep list/)).toBeInTheDocument();
  });

  it('says so when an operation has no log', async () => {
    stubFetch({ history: page([anOperation({ log: [] })]) });
    const drawer = await openOperation();

    await openTab(drawer, /what happened/i);
    expect(within(drawer).getByText(/no log was recorded/i)).toBeInTheDocument();
  });

  it('opens a row from the keyboard', async () => {
    stubFetch();
    renderRouted(<HistoryPage />);

    const row = await screen.findByRole('row', { name: /open show - s01e01/i });
    row.focus();
    await userEvent.keyboard('{Enter}');

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('shows an unfinished job and opens its live log', async () => {
    stubFetch({ jobs: { items: [aJob()], total: 1, limit: 20, offset: 0 } });
    renderRouted(<HistoryPage />);

    await userEvent.click(await screen.findByText('Show S01E02.mkv'));

    const drawer = await screen.findByRole('dialog');
    expect(await within(drawer).findByText('Import in progress')).toBeInTheDocument();
    expect(within(drawer).getAllByText('embedding subtitles English').length).toBeGreaterThan(0);
  });

  it('clears the history only after confirming', async () => {
    const fetchStub = stubFetch();
    renderRouted(<HistoryPage />);

    await userEvent.click(await screen.findByRole('button', { name: /history actions/i }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /clear history/i }));
    const deleted = () => fetchStub.mock.calls.some(([, init]) => init?.method === 'DELETE');
    expect(deleted()).toBe(false);

    await userEvent.click(await screen.findByRole('button', { name: /delete everything/i }));
    expect(deleted()).toBe(true);
  });

  it('distinguishes an empty history from an empty search', async () => {
    stubFetch({ history: page([]) });
    renderRouted(<HistoryPage />);

    expect(await screen.findByText('No imports yet')).toBeInTheDocument();

    await userEvent.type(screen.getByRole('textbox', { name: /search history/i }), 'dune');
    expect(await screen.findByText('Nothing matches these filters')).toBeInTheDocument();
  });
});
