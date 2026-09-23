import { Badge } from '@mantine/core';
import type { App } from '../api/types';

// Each app's own brand colour, so the column scans at a glance.
const APPS: Record<App, { label: string; color: string }> = {
  radarr: { label: 'Radarr', color: 'yellow' },
  sonarr: { label: 'Sonarr', color: 'cyan' },
};

export function AppBadge({ app }: { app: App }) {
  const { label, color } = APPS[app];
  return (
    <Badge variant="dot" color={color} tt="none" fw={500}>
      {label}
    </Badge>
  );
}
