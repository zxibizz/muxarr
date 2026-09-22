import { Card, Stack, Text, Title } from '@mantine/core';
import type { ReactNode } from 'react';

interface Props {
  title: string;
  description?: string;
  children: ReactNode;
}

export function SettingsSection({ title, description, children }: Props) {
  return (
    <Card withBorder padding="lg">
      <Stack gap="md">
        <div>
          <Title order={5}>{title}</Title>
          {description && (
            <Text size="sm" c="dimmed" mt={4}>
              {description}
            </Text>
          )}
        </div>
        {children}
      </Stack>
    </Card>
  );
}
