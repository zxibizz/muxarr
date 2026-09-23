import { Alert, Badge, Card, Group, List, SimpleGrid, Skeleton, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconCircleX,
  IconFolder,
  IconHeartbeat,
  IconHourglass,
  IconPlayerPlay,
} from '@tabler/icons-react';
import { describeError } from '../../api/client';
import { useHealth, useSystem } from '../../api/queries';
import type { SystemStatus } from '../../api/types';
import { KeyValue } from '../../components/KeyValue';
import { PageHeader } from '../../components/PageHeader';
import { StatCard } from '../../components/StatCard';
import { formatRelative, formatTimestamp } from '../../lib/format';

function WorkerCard({ system }: { system: SystemStatus | undefined }) {
  const worker = system?.worker;
  const alive = worker?.alive ?? false;

  return (
    <Card>
      <Group gap="md" align="flex-start" wrap="nowrap">
        <ThemeIcon size={44} radius="md" variant="light" color={alive ? 'teal' : 'red'}>
          <IconHeartbeat size={24} />
        </ThemeIcon>
        <Stack gap="md" style={{ flex: 1 }}>
          <Stack gap={2}>
            <Group gap="xs">
              <Title order={2}>Worker</Title>
              {worker && (
                <Badge color={alive ? 'teal' : 'red'} variant="filled">
                  {alive ? 'running' : 'offline'}
                </Badge>
              )}
            </Group>
            <Text size="sm" c="dimmed">
              The only process that muxes. The API queues imports; the worker runs them.
            </Text>
          </Stack>

          {worker ? (
            <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="lg">
              <KeyValue label="Last heartbeat">
                {worker.last_seen_at ? (
                  <span title={formatTimestamp(worker.last_seen_at)}>
                    {formatRelative(worker.last_seen_at)}
                  </span>
                ) : (
                  'never'
                )}
              </KeyValue>
              <KeyValue label="Considered dead after">
                {worker.stale_after_seconds}s of silence
              </KeyValue>
              <KeyValue label="Concurrent muxes">{worker.max_concurrent_muxes}</KeyValue>
            </SimpleGrid>
          ) : (
            <Skeleton height={40} />
          )}
        </Stack>
      </Group>
    </Card>
  );
}

export function SystemPage() {
  const system = useSystem();
  const health = useHealth();
  const queue = system.data?.queue;
  const error = describeError(system.error);

  return (
    <Stack gap="xl">
      <PageHeader
        title="System"
        description="Whether imports can run, and what is waiting on them."
      />

      {error && (
        <Alert color="red" icon={<IconAlertTriangle size={18} />} title="Could not reach the daemon">
          {error}
        </Alert>
      )}

      {system.data && !system.data.worker.alive && (
        <Alert color="red" icon={<IconAlertTriangle size={18} />} title="Nothing is muxing">
          Submitted imports wait in <strong>pending</strong> until the worker comes back. Check its
          logs with <code>docker logs</code>.
        </Alert>
      )}

      <WorkerCard system={system.data} />

      <Stack gap="sm">
        <Title order={2}>Job queue</Title>
        <SimpleGrid cols={{ base: 2, md: 4 }} spacing="md">
          <StatCard label="Pending" value={queue?.pending} icon={IconHourglass} color="yellow" />
          <StatCard label="Running" value={queue?.running} icon={IconPlayerPlay} color="brand" />
          <StatCard label="Succeeded" value={queue?.succeeded} icon={IconCircleCheck} color="teal" />
          <StatCard label="Failed" value={queue?.failed} icon={IconCircleX} color="red" />
        </SimpleGrid>
        <Text size="xs" c="dimmed">
          Finished jobs are pruned after their retention period, so these cover a recent window.
        </Text>
      </Stack>

      <Card>
        <Stack gap="md">
          <Title order={2}>Daemon</Title>
          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="lg">
            <KeyValue label="Version">{health.data ? `v${health.data.version}` : '—'}</KeyValue>
            <KeyValue label="Authentication">
              {health.data ? (health.data.auth_required ? 'token required' : 'open') : '—'}
            </KeyValue>
          </SimpleGrid>
          <KeyValue label="Read roots">
            {health.data && health.data.read_roots.length > 0 ? (
              <List spacing={4} size="sm" icon={<IconFolder size={14} />} center>
                {health.data.read_roots.map((root) => (
                  <List.Item key={root}>
                    <Text size="sm" ff="monospace">
                      {root}
                    </Text>
                  </List.Item>
                ))}
              </List>
            ) : (
              '—'
            )}
          </KeyValue>
        </Stack>
      </Card>
    </Stack>
  );
}
