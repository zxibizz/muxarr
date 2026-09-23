import { Group, Stack, Text, Title } from '@mantine/core';
import type { ReactNode } from 'react';

interface Props {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({ title, description, actions }: Props) {
  return (
    <Group justify="space-between" align="flex-end" wrap="wrap" gap="md">
      <Stack gap={4}>
        <Title order={1}>{title}</Title>
        {description && (
          <Text c="dimmed" size="sm" maw={640}>
            {description}
          </Text>
        )}
      </Stack>
      {actions}
    </Group>
  );
}
