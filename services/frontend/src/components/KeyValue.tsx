import { ActionIcon, Code, CopyButton, Group, Stack, Text, Tooltip } from '@mantine/core';
import { IconCheck, IconCopy } from '@tabler/icons-react';
import type { ReactNode } from 'react';

export function KeyValue({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Stack gap={2}>
      <Text size="xs" c="dimmed" fw={600}>
        {label}
      </Text>
      <Text size="sm" component="div">
        {children}
      </Text>
    </Stack>
  );
}

export function CopyPath({ label, path }: { label: string; path: string }) {
  return (
    <Stack gap={4}>
      <Text size="xs" c="dimmed" fw={600}>
        {label}
      </Text>
      <Group gap={6} wrap="nowrap" align="flex-start">
        <Code block style={{ flex: 1, wordBreak: 'break-all', whiteSpace: 'pre-wrap' }}>
          {path}
        </Code>
        <CopyButton value={path}>
          {({ copied, copy }) => (
            <Tooltip label={copied ? 'Copied' : 'Copy path'}>
              <ActionIcon
                variant="subtle"
                color={copied ? 'teal' : 'gray'}
                onClick={copy}
                aria-label={`Copy ${label.toLowerCase()}`}
              >
                {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
              </ActionIcon>
            </Tooltip>
          )}
        </CopyButton>
      </Group>
    </Stack>
  );
}
