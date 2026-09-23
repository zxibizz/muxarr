import { Accordion, Badge, Box, Group, ScrollArea, Stack, Text, ThemeIcon, Timeline } from '@mantine/core';
import {
  IconArrowMerge,
  IconFileImport,
  IconFilter,
  IconFlag,
  IconFolderSearch,
  IconMovie,
  IconShieldCheck,
  IconSparkles,
} from '@tabler/icons-react';
import type { Icon } from '@tabler/icons-react';
import type { LogEntry, LogStage } from '../../api/types';
import { formatClock, formatContextValue } from '../../lib/format';

const STAGES: Record<LogStage, { label: string; icon: Icon }> = {
  guard: { label: 'Paths', icon: IconShieldCheck },
  probe: { label: 'Source', icon: IconMovie },
  discovery: { label: 'Discovery', icon: IconFolderSearch },
  ai: { label: 'AI provider', icon: IconSparkles },
  selection: { label: 'Selection', icon: IconFilter },
  mux: { label: 'Remux', icon: IconArrowMerge },
  placement: { label: 'Placement', icon: IconFileImport },
  outcome: { label: 'Outcome', icon: IconFlag },
};

function levelColour(level: string): string {
  if (level === 'ERROR' || level === 'CRITICAL') return 'red';
  if (level === 'WARNING') return 'yellow';
  if (level === 'DEBUG' || level === 'TRACE') return 'gray';
  return 'brand';
}

function ContextChips({ context }: { context: Record<string, string> }) {
  const entries = Object.entries(context);
  if (entries.length === 0) return null;
  return (
    <Group gap={4} mt={6}>
      {entries.map(([key, value]) => (
        <Badge key={key} variant="default" tt="none" fw={400} size="sm" radius="sm">
          <Text span c="dimmed" inherit>
            {key.replaceAll('_', ' ')}
          </Text>{' '}
          {formatContextValue(value)}
        </Badge>
      ))}
    </Group>
  );
}

function RawLog({ entries }: { entries: LogEntry[] }) {
  return (
    <ScrollArea.Autosize mah={360} type="auto">
      <Box
        p="sm"
        bg="dark.8"
        ff="monospace"
        fz="xs"
        style={{ borderRadius: 'var(--mantine-radius-md)' }}
      >
        {entries.map((entry, index) => (
          <Group key={`${entry.ts}-${index}`} gap={8} wrap="nowrap" align="flex-start">
            <Text inherit c="dimmed" style={{ flexShrink: 0 }}>
              {formatClock(entry.ts)}
            </Text>
            <Text inherit c={levelColour(entry.level)} w={64} style={{ flexShrink: 0 }}>
              {entry.level}
            </Text>
            <Text inherit style={{ wordBreak: 'break-word' }}>
              {entry.message}
              {Object.entries(entry.context).map(([key, value]) => (
                <Text key={key} span inherit c="dimmed">
                  {'  '}
                  {key}={value}
                </Text>
              ))}
            </Text>
          </Group>
        ))}
      </Box>
    </ScrollArea.Autosize>
  );
}

interface Props {
  entries: LogEntry[];
  empty?: string;
}

export function ActivityLog({ entries, empty = 'No log was recorded for this import.' }: Props) {
  if (entries.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        {empty}
      </Text>
    );
  }

  const story = entries.filter(
    (entry): entry is LogEntry & { stage: LogStage } => entry.stage !== null,
  );

  return (
    <Stack gap="lg">
      {story.length > 0 && (
        <Timeline active={story.length} bulletSize={26} lineWidth={2}>
          {story.map((entry, index) => {
            const { label, icon: StageIcon } = STAGES[entry.stage];
            const colour = levelColour(entry.level);
            return (
              <Timeline.Item
                key={`${entry.ts}-${index}`}
                color={colour}
                bullet={
                  <ThemeIcon size={26} radius="xl" color={colour} variant="light">
                    <StageIcon size={14} stroke={2} />
                  </ThemeIcon>
                }
                title={
                  <Group gap={8}>
                    <Text size="sm" fw={600}>
                      {label}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {formatClock(entry.ts)}
                    </Text>
                  </Group>
                }
              >
                <Text size="sm" style={{ wordBreak: 'break-word' }}>
                  {entry.message}
                </Text>
                <ContextChips context={entry.context} />
              </Timeline.Item>
            );
          })}
        </Timeline>
      )}

      <Accordion variant="separated" radius="md">
        <Accordion.Item value="full">
          <Accordion.Control>
            <Text size="sm">Full log · {entries.length} lines</Text>
          </Accordion.Control>
          <Accordion.Panel>
            <RawLog entries={entries} />
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  );
}
