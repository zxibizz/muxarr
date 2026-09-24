import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  displayName,
  formatBytes,
  formatClock,
  formatContextValue,
  formatDuration,
  formatRelative,
  formatSizeDelta,
  formatTimestamp,
  shortenPath,
} from './format';

describe('displayName', () => {
  it('prefers the file muxarr produced, without its extension', () => {
    expect(
      displayName({ media_file: '/tv/Show - S01E01.mkv', destination_path: '/tv/Show - S01E01.mp4' }),
    ).toBe('Show - S01E01');
  });

  it('falls back to the destination *arr asked for', () => {
    expect(displayName({ media_file: null, destination_path: '/movies/Dune (2024).mp4' })).toBe(
      'Dune (2024)',
    );
  });
});

describe('formatSizeDelta', () => {
  it('signs the difference', () => {
    expect(formatSizeDelta(1024, 3072)).toBe('+2.0 KB');
    expect(formatSizeDelta(3072, 1024)).toBe('−2.0 KB');
    expect(formatSizeDelta(10, 10)).toBe('same size');
  });

  it('says nothing when either side is unknown', () => {
    expect(formatSizeDelta(null, 10)).toBeNull();
  });
});

describe('formatContextValue', () => {
  it('turns Python booleans into words', () => {
    expect(formatContextValue('True')).toBe('yes');
    expect(formatContextValue('False')).toBe('no');
    expect(formatContextValue('Matroska')).toBe('Matroska');
  });
});

describe('formatBytes', () => {
  it('renders a dash for an unknown size', () => {
    expect(formatBytes(null)).toBe('—');
  });

  it('keeps bytes exact below a kilobyte', () => {
    expect(formatBytes(512)).toBe('512 B');
  });

  it('drops the decimal once the number is large enough not to need it', () => {
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(20 * 1024)).toBe('20 KB');
  });

  it('stops at the largest unit it knows', () => {
    expect(formatBytes(5 * 1024 ** 5)).toMatch(/TB$/);
  });
});

describe('formatDuration', () => {
  it('uses milliseconds, seconds and minutes as the value grows', () => {
    expect(formatDuration(250)).toBe('250 ms');
    expect(formatDuration(1500)).toBe('1.5 s');
    expect(formatDuration(90_000)).toBe('1m 30s');
  });
});

describe('formatRelative', () => {
  it('bands the age of a timestamp', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-22T12:00:00Z'));

    expect(formatRelative('2026-09-22T11:59:30Z')).toBe('just now');
    expect(formatRelative('2026-09-22T11:30:00Z')).toBe('30m ago');
    expect(formatRelative('2026-09-22T09:00:00Z')).toBe('3h ago');
    expect(formatRelative('2026-09-19T12:00:00Z')).toBe('3d ago');

    vi.useRealTimers();
  });

  it('passes an unparseable value straight through', () => {
    expect(formatRelative('not a date')).toBe('not a date');
  });
});

describe("timestamps in the viewer's time zone", () => {
  // Node re-reads TZ on assignment, so this moves the "browser" to Tokyo (UTC+9).
  beforeEach(() => {
    vi.stubEnv('TZ', 'Asia/Tokyo');
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('converts UTC to local wall-clock time', () => {
    expect(formatClock('2026-09-22T10:00:00Z')).toMatch(/19:00:00|7:00:00/);
    expect(formatClock('2026-09-22T12:00:00+02:00')).toMatch(/19:00:00|7:00:00/);
  });

  it('reads an offset-less value as UTC, not as local time', () => {
    expect(formatClock('2026-09-22 10:00:00')).toBe(formatClock('2026-09-22T10:00:00Z'));
    expect(formatTimestamp('2026-09-22T10:00:00')).toBe(formatTimestamp('2026-09-22T10:00:00Z'));
  });

  it('names the zone on a full timestamp', () => {
    expect(formatTimestamp('2026-09-22T10:00:00Z')).toMatch(/GMT\+9|JST/);
  });

  it('passes an unparseable value straight through', () => {
    expect(formatTimestamp('garbage')).toBe('garbage');
  });
});

describe('shortenPath', () => {
  it('leaves short paths alone', () => {
    expect(shortenPath('/media/file.mkv')).toBe('/media/file.mkv');
  });

  it('keeps the last two segments of a long path', () => {
    expect(shortenPath('/media/Show/Season 01/Show - S01E01.mkv')).toBe(
      '…/Season 01/Show - S01E01.mkv',
    );
  });
});
