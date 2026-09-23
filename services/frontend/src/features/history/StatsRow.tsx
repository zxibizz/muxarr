import { SimpleGrid } from '@mantine/core';
import { IconArrowForwardUp, IconArrowMerge, IconBadgeCc, IconDownload } from '@tabler/icons-react';
import { useStats } from '../../api/queries';
import { StatCard } from '../../components/StatCard';
import { formatPercent } from '../../lib/format';

export function StatsRow() {
  const { data: stats } = useStats();

  const perMux = stats && stats.muxed > 0 ? (stats.tracks_added / stats.muxed).toFixed(1) : null;

  return (
    <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }} spacing="md">
      <StatCard
        label="Imports"
        value={stats?.total}
        icon={IconDownload}
        color="brand"
        hint={stats && `${stats.last_24h.toLocaleString()} in the last 24 hours`}
      />
      <StatCard
        label="Muxed"
        value={stats?.muxed}
        icon={IconArrowMerge}
        color="teal"
        hint={stats && `${formatPercent(stats.muxed, stats.total)} of imports`}
      />
      <StatCard
        label="Skipped"
        value={stats?.deferred}
        icon={IconArrowForwardUp}
        color="blue"
        hint="Left for *arr to import untouched"
      />
      <StatCard
        label="Tracks embedded"
        value={stats?.tracks_added}
        icon={IconBadgeCc}
        color="grape"
        hint={perMux ? `${perMux} per muxed import` : 'None yet'}
      />
    </SimpleGrid>
  );
}
