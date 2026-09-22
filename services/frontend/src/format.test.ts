import { describe, expect, it, vi } from 'vitest';
import { formatBytes, formatDuration, formatRelative, shortenPath } from './format';

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
