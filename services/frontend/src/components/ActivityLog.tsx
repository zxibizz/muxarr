import { Accordion, Badge, Group, ScrollArea, Stack, Text, Timeline } from '@mantine/core';
import { formatClock } from '../format';
import type { LogEntry, LogStage } from '../types';

const STAGE_LABELS: Record<LogStage, string> = {
  guard: 'Paths',
  probe: 'Source',
  discovery: 'Discovery',
  ai: 'AI provider',
  selection: 'Selection',
  mux: 'Remux',
  placement: 'Placement',
  outcome: 'Outcome',
};

function levelColour(level: string): string {
  if (level === 'ERROR' || level === 'CRITICAL') return 'red';
  if (level === 'WARNING') return 'yellow';
  if (level === 'DEBUG' || level === 'TRACE') return 'gray';
  return 'teal';
}

function renderContext(context: Record<string, string>): string {
  return Object.entries(context)
    .map(([key, value]) => `${key}=${value}`)
    .join('  ');
}

interface Props {
  entries: LogEntry[];
  /** Shown instead of the timeline when there is nothing recorded. */
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

  const story = entries.filter((entry) => entry.stage !== null);

  return (
    <Stack gap="md">
      {story.length > 0 && (
        <Timeline active={story.length} bulletSize={12} lineWidth={2}>
          {story.map((entry, index) => (
            <Timeline.Item
              key={`${entry.ts}-${index}`}
              color={levelColour(entry.level)}
              title={
                <Group gap={6}>
                  <Text size="xs" tt="uppercase" fw={700} c="dimmed">
                    {STAGE_LABELS[entry.stage as LogStage]}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {formatClock(entry.ts)}
                  </Text>
                </Group>
              }
            >
              <Text size="sm">{entry.message}</Text>
              {Object.keys(entry.context).length > 0 && (
                <Text size="xs" c="dimmed" ff="monospace">
                  {renderContext(entry.context)}
                </Text>
              )}
            </Timeline.Item>
          ))}
        </Timeline>
      )}

      <Accordion variant="contained">
        <Accordion.Item value="full">
          <Accordion.Control>
            <Text size="sm">Full log ({entries.length} lines)</Text>
          </Accordion.Control>
          <Accordion.Panel>
            <ScrollArea.Autosize mah={320} type="auto">
              <Stack gap={2}>
                {entries.map((entry, index) => (
                  <Group key={`${entry.ts}-${index}`} gap={8} wrap="nowrap" align="flex-start">
                    <Text size="xs" c="dimmed" ff="monospace" style={{ flexShrink: 0 }}>
                      {formatClock(entry.ts)}
                    </Text>
                    <Badge
                      size="xs"
                      variant="light"
                      color={levelColour(entry.level)}
                      style={{ flexShrink: 0 }}
                    >
                      {entry.level}
                    </Badge>
                    <Text size="xs" ff="monospace">
                      {entry.message}
                      {Object.keys(entry.context).length > 0 && (
                        <Text span size="xs" c="dimmed" ff="monospace">
                          {'  '}
                          {renderContext(entry.context)}
                        </Text>
                      )}
                    </Text>
                  </Group>
                ))}
              </Stack>
            </ScrollArea.Autosize>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  );
}
