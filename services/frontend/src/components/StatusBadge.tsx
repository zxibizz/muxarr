import { Badge } from '@mantine/core';
import type { BadgeVariant } from '@mantine/core';
import { IconArrowForwardUp, IconCheck, IconTransfer } from '@tabler/icons-react';
import type { MoveStatus } from '../api/types';

interface Style {
  label: string;
  color: string;
  variant: BadgeVariant;
  icon: typeof IconCheck;
}

// Skipping is muxarr's normal, safe answer, so it reads as neutral rather than as a warning.
const STATUS: Record<MoveStatus, Style> = {
  RenameRequested: { label: 'Muxed', color: 'teal', variant: 'light', icon: IconCheck },
  DeferMove: { label: 'Skipped', color: 'gray', variant: 'default', icon: IconArrowForwardUp },
  MoveComplete: { label: 'Moved', color: 'blue', variant: 'light', icon: IconTransfer },
};

export function StatusBadge({ status }: { status: MoveStatus }) {
  const { label, color, variant, icon: Icon } = STATUS[status];
  return (
    <Badge color={color} variant={variant} leftSection={<Icon size={12} stroke={2.5} />}>
      {label}
    </Badge>
  );
}
