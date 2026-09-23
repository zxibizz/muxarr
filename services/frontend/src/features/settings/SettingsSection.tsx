import { Box, Card, Code, Flex, Stack, Text, Title } from '@mantine/core';
import { IconLock } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import classes from './settings.module.css';
import type { FieldBinding } from './useSettingsForm';

interface SectionProps {
  title: string;
  description?: ReactNode;
  children: ReactNode;
}

export function SettingsSection({ title, description, children }: SectionProps) {
  return (
    <Card padding={0}>
      <Stack gap={2} px="lg" pt="lg" pb="xs">
        <Title order={2}>{title}</Title>
        {description && (
          <Text size="sm" c="dimmed">
            {description}
          </Text>
        )}
      </Stack>
      <Box className={classes.rows} px="lg" pb="xs">
        {children}
      </Box>
    </Card>
  );
}

interface RowProps {
  binding: FieldBinding;
  label: string;
  description?: ReactNode;
  /** A toggle needs no column of its own. */
  inline?: boolean;
  children: ReactNode;
}

/** Label and explanation on the left, the control on the right. */
export function SettingRow({ binding, label, description, inline, children }: RowProps) {
  return (
    <Flex
      direction={inline ? 'row' : { base: 'column', sm: 'row' }}
      gap={{ base: 'xs', sm: 'xl' }}
      justify="space-between"
      align={{ base: 'stretch', sm: 'center' }}
      py="md"
    >
      <Stack gap={2} style={{ flex: 1 }}>
        <Text component="label" htmlFor={binding.id} size="sm" fw={600}>
          {label}
        </Text>
        {description && (
          <Text size="xs" c="dimmed" maw={520}>
            {description}
          </Text>
        )}
        {binding.locked && (
          <Text size="xs" c="yellow.5" mt={2}>
            <IconLock size={12} style={{ verticalAlign: '-1px', marginRight: 4 }} />
            Pinned by <Code fz="xs">{binding.envVar}</Code>
          </Text>
        )}
      </Stack>
      <Box w={inline ? 'auto' : { base: '100%', sm: 300 }} style={{ flexShrink: 0 }}>
        {children}
      </Box>
    </Flex>
  );
}
