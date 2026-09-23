import type { AddedTrack, Operation, RejectCode } from '../api/types';

const UNITS = ['B', 'KB', 'MB', 'GB', 'TB'];
export function formatBytes(bytes: number | null): string {
  if (bytes === null || Number.isNaN(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;

  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${UNITS[unit]}`;
}

/** How much bigger or smaller the output is, e.g. "+12 MB". */
export function formatSizeDelta(before: number | null, after: number | null): string | null {
  if (before === null || after === null) return null;
  const delta = after - before;
  if (delta === 0) return 'same size';
  return `${delta > 0 ? '+' : '−'}${formatBytes(Math.abs(delta))}`;
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${Math.round(seconds % 60)}s`;
}

export function formatTimestamp(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : when.toLocaleString();
}

/** Wall-clock time only; log lines are all from the same import. */
export function formatClock(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : when.toLocaleTimeString();
}

export function formatRelative(iso: string): string {
  const when = new Date(iso).getTime();
  if (Number.isNaN(when)) return iso;

  const seconds = Math.round((Date.now() - when) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86_400)}d ago`;
}

export function formatPercent(part: number, whole: number): string {
  if (whole === 0) return '—';
  return `${Math.round((part / whole) * 100)}%`;
}

/** Trim a long path to its last two segments, keeping it readable in a table. */
export function shortenPath(path: string): string {
  const parts = path.split('/').filter(Boolean);
  return parts.length <= 2 ? path : `…/${parts.slice(-2).join('/')}`;
}

export function fileStem(path: string): string {
  const name = path.split('/').filter(Boolean).pop() ?? path;
  return name.replace(/\.[^./]+$/, '');
}

/** The name *arr gave the file, which reads far better than the release name. */
export function displayName(operation: Pick<Operation, 'media_file' | 'destination_path'>): string {
  return fileStem(operation.media_file ?? operation.destination_path);
}

/** Log context arrives as Python's str(); a bare True/False reads badly in a UI. */
export function formatContextValue(value: string): string {
  if (value === 'True') return 'yes';
  if (value === 'False') return 'no';
  return value;
}

export function trackFlags(track: Pick<AddedTrack, 'forced' | 'hearing_impaired' | 'variant'>) {
  const flags: string[] = [];
  if (track.forced) flags.push('forced');
  if (track.hearing_impaired) flags.push('SDH');
  if (track.variant) flags.push(track.variant);
  return flags;
}

/** Why an embedded track looks the way it does, in one line. */
export function explainTrack(track: AddedTrack): string {
  const parts = [`${track.kind} · ${track.label}`];
  if (track.language && track.language !== track.label) parts.push(`(${track.language})`);
  if (track.forced) parts.push('· forced');
  if (track.hearing_impaired) parts.push('· hearing impaired');
  if (track.variant) parts.push(`· ${track.variant}`);
  parts.push(
    track.source === 'ai'
      ? '— identified by the AI provider'
      : '— identified from its filename',
  );
  if (track.file) parts.push(`from ${track.file}`);
  return parts.join(' ');
}

export const REJECT_LABELS: Record<RejectCode, string> = {
  image_subtitle: 'Image subtitle',
  undetermined_language: 'Unknown language',
  language_not_kept: 'Not in keep list',
  already_present: 'Already in file',
  track_limit: 'Track limit',
  file_missing: 'File missing',
  file_empty: 'Empty file',
  uninspectable: 'Unreadable',
  no_tracks: 'No readable track',
};

/** Deliberate choices read calmly; anything that went wrong with a file stands out. */
export function rejectColour(code: RejectCode | null): string {
  if (code === 'file_missing' || code === 'file_empty') return 'orange';
  if (code === 'uninspectable' || code === 'no_tracks') return 'red';
  return 'gray';
}
