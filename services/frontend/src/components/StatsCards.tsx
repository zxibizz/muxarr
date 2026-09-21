import { Card, Group, SimpleGrid, Skeleton, Text } from '@mantine/core';
import type { Stats } from '../types';

interface Props {
  stats: Stats | null;
}

export function StatsCards({ stats }: Props) {
  const cards = [
    { label: 'Imports seen', value: stats?.total },
    { label: 'Muxed', value: stats?.muxed },
    { label: 'Skipped', value: stats?.deferred },
    { label: 'Tracks embedded', value: stats?.tracks_added },
    { label: 'Last 24h', value: stats?.last_24h },
  ];

  return (
    <SimpleGrid cols={{ base: 2, sm: 3, md: 5 }} spacing="md">
      {cards.map((card) => (
        <Card key={card.label} padding="md" radius="md" withBorder>
          <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
            {card.label}
          </Text>
          <Group gap="xs" mt="xs">
            {card.value === undefined ? (
              <Skeleton height={28} width={60} />
            ) : (
              <Text size="xl" fw={700}>
                {card.value.toLocaleString()}
              </Text>
            )}
          </Group>
        </Card>
      ))}
    </SimpleGrid>
  );
}
