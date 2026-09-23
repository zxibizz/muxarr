import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { AuthGateProvider } from '../auth';
import { HistoryPage } from './HistoryPage';
import { aJob, aLogEntry, anOperation, renderRouted, stubFetch } from '../test/helpers';

function render() {
  renderRouted(
    <AuthGateProvider>
      <HistoryPage />
    </AuthGateProvider>,
  );
}

describe('HistoryPage', () => {
  it('names the track and how it was identified, without an "[ai]" suffix', async () => {
    stubFetch();
    render();

    const badge = await screen.findByText('audio: Russian');
    expect(badge).toBeInTheDocument();
    expect(screen.queryByText(/\[ai\]/i)).not.toBeInTheDocument();
  });

  it('explains what happened when an operation is opened', async () => {
    stubFetch({
      history: {
        items: [
          anOperation({
            log: [
              aLogEntry({ stage: 'probe', message: 'source already holds 1 audio track' }),
              aLogEntry({ message: 'skipping subtitles eng.srt: already present in container' }),
            ],
          }),
        ],
        total: 1,
        limit: 25,
        offset: 0,
      },
    });
    render();

    await userEvent.click(await screen.findByText('Show S01E01'));

    const drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByText('What happened')).toBeInTheDocument();
    // Once in the narrative, once in the full log below it.
    expect(within(drawer).getAllByText('source already holds 1 audio track')).toHaveLength(2);
    expect(within(drawer).getByText(/identified by the AI provider/i)).toBeInTheDocument();
  });

  it('shows an unfinished job and opens its live log', async () => {
    stubFetch({
      jobs: { items: [aJob()], total: 1, limit: 20, offset: 0 },
    });
    render();

    await userEvent.click(await screen.findByText('Show S01E02.mkv'));

    const drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByText('Import in progress')).toBeInTheDocument();
    expect(within(drawer).getAllByText('embedding subtitles English')).toHaveLength(2);
  });

  it('lists the source tracks the keep lists stripped', async () => {
    stubFetch({
      history: {
        items: [
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
        ],
        total: 1,
        limit: 25,
        offset: 0,
      },
    });
    render();

    await userEvent.click(await screen.findByText('Show S01E01'));

    const drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByText('Removed from source (1)')).toBeInTheDocument();
    expect(within(drawer).getByText(/track 2, language is not in the keep list/)).toBeInTheDocument();
  });

  it('says so when an operation has no log', async () => {
    stubFetch({
      history: { items: [anOperation({ log: [] })], total: 1, limit: 25, offset: 0 },
    });
    render();

    await userEvent.click(await screen.findByText('Show S01E01'));

    const drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByText(/no log was recorded/i)).toBeInTheDocument();
  });
});
