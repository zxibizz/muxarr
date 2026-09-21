import { Alert, Badge, Divider, Drawer, Group, Stack, Text, Title } from '@mantine/core';
import { formatRelative, formatTimestamp } from '../format';
import type { SystemStatus } from '../types';

interface Props {
  system: SystemStatus | null;
  opened: boolean;
  onClose: () => void;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
        {label}
      </Text>
      <div style={{ marginTop: 4 }}>{children}</div>
    </div>
  );
}

function Count({ label, value }: { label: string; value: number }) {
  return (
    <Field label={label}>
      <Text size="xl" fw={700}>
        {value.toLocaleString()}
      </Text>
    </Field>
  );
}

export function SystemDrawer({ system, opened, onClose }: Props) {
  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      position="right"
      size="md"
      padding="lg"
      title={<Title order={4}>System</Title>}
    >
      {system && (
        <Stack gap="md">
          <Group gap="xs">
            <Badge color={system.worker.alive ? 'green' : 'red'}>
              {system.worker.alive ? 'worker running' : 'worker offline'}
            </Badge>
            <Badge variant="outline">v{system.version}</Badge>
          </Group>

          {!system.worker.alive && (
            <Alert color="red" title="Nothing is muxing">
              The API queues imports but only the worker runs them. Submitted imports
              will sit in <strong>pending</strong> until it comes back.
            </Alert>
          )}

          <Field label="Worker last seen">
            <Text size="sm">
              {system.worker.last_seen_at
                ? `${formatRelative(system.worker.last_seen_at)} (${formatTimestamp(
                    system.worker.last_seen_at,
                  )})`
                : 'never — the worker has not started since this database was created'}
            </Text>
          </Field>

          <Group grow>
            <Field label="Considered dead after">
              <Text size="sm">{system.worker.stale_after_seconds}s without a heartbeat</Text>
            </Field>
            <Field label="Concurrent muxes">
              <Text size="sm">{system.worker.max_concurrent_muxes}</Text>
            </Field>
          </Group>

          <Divider label="Job queue" labelPosition="left" />

          <Group grow>
            <Count label="Pending" value={system.queue.pending} />
            <Count label="Running" value={system.queue.running} />
          </Group>

          <Group grow>
            <Count label="Succeeded" value={system.queue.succeeded} />
            <Count label="Failed" value={system.queue.failed} />
          </Group>

          <Text size="xs" c="dimmed">
            Finished jobs are pruned once their TTL expires, so these are not lifetime
            totals. A job in <strong>failed</strong> means the daemon itself broke — a
            deferred import is a success here and shows up in the history instead.
          </Text>
        </Stack>
      )}
    </Drawer>
  );
}
