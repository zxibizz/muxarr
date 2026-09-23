import { Stack, Text, ThemeIcon } from '@mantine/core';
import type { Icon } from '@tabler/icons-react';
import type { ReactNode } from 'react';

interface Props {
  icon: Icon;
  title: string;
  children?: ReactNode;
}

export function EmptyState({ icon: IconComponent, title, children }: Props) {
  return (
    <Stack align="center" gap="xs" py={48} px="md">
      <ThemeIcon size={48} radius="xl" variant="light" color="brand">
        <IconComponent size={24} stroke={1.5} />
      </ThemeIcon>
      <Text fw={600} mt="xs">
        {title}
      </Text>
      {children && (
        <Text size="sm" c="dimmed" ta="center" maw={460}>
          {children}
        </Text>
      )}
    </Stack>
  );
}
