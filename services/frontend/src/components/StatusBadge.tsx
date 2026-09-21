import { Badge } from '@mantine/core';
import type { MoveStatus } from '../types';

const COLOURS: Record<MoveStatus, string> = {
  RenameRequested: 'teal',
  MoveComplete: 'blue',
  DeferMove: 'gray',
};

const LABELS: Record<MoveStatus, string> = {
  RenameRequested: 'Muxed',
  MoveComplete: 'Muxed',
  // "Skipped" rather than "Deferred": from the user's side nothing happened.
  DeferMove: 'Skipped',
};

export function StatusBadge({ status }: { status: MoveStatus }) {
  return (
    <Badge color={COLOURS[status] ?? 'gray'} variant="light">
      {LABELS[status] ?? status}
    </Badge>
  );
}
