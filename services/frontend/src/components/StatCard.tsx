import { Card, Group, Skeleton, Stack, Text, ThemeIcon } from '@mantine/core';
import type { Icon } from '@tabler/icons-react';
import type { ReactNode } from 'react';

interface Props {
  label: string;
  value: number | undefined;
  icon: Icon;
  color: string;
  hint?: ReactNode;
}

export function StatCard({ label, value, icon: IconComponent, color, hint }: Props) {
  return (
    <Card padding="md">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap={2}>
          <Text size="xs" c="dimmed" tt="uppercase" fw={700} lts={0.4}>
            {label}
          </Text>
          {value === undefined ? (
            <Skeleton height={30} width={64} mt={4} />
          ) : (
            <Text fz={28} fw={700} lh={1.2} style={{ fontVariantNumeric: 'tabular-nums' }}>
              {value.toLocaleString()}
            </Text>
          )}
        </Stack>
        <ThemeIcon size={36} radius="md" variant="light" color={color}>
          <IconComponent size={20} stroke={1.75} />
        </ThemeIcon>
      </Group>
      {hint && (
        <Text size="xs" c="dimmed" mt={6}>
          {hint}
        </Text>
      )}
    </Card>
  );
}
