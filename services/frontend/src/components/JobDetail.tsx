import { Badge, Code, Divider, Drawer, Group, Stack, Text, Title } from '@mantine/core';
import { useEffect, useState } from 'react';
import { api } from '../api';
import { formatTimestamp } from '../format';
import type { Job } from '../types';
import { ActivityLog } from './ActivityLog';

// Fast enough to feel live, slow enough that a queue of them costs nothing.
const POLL_INTERVAL_MS = 2_000;

interface Props {
  job: Job | null;
  onClose: () => void;
}

export function JobDetail({ job, onClose }: Props) {
  const [current, setCurrent] = useState<Job | null>(job);

  useEffect(() => setCurrent(job), [job]);

  const id = current?.id;
  const state = current?.state;

  useEffect(() => {
    if (!id || state === 'succeeded' || state === 'failed') return undefined;
    const timer = window.setInterval(() => {
      void api
        .job(id)
        .then(setCurrent)
        // A blip while a mux runs is not worth interrupting the view for.
        .catch(() => undefined);
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [id, state]);

  return (
    <Drawer
      opened={job !== null}
      onClose={onClose}
      position="right"
      size="lg"
      padding="lg"
      title={<Title order={4}>Import in progress</Title>}
    >
      {current && (
        <Stack gap="md">
          <Group gap="xs">
            <Badge variant="light">{current.state}</Badge>
            <Badge variant="outline">{current.app}</Badge>
            {current.dry_run && <Badge color="yellow">dry run</Badge>}
          </Group>

          <Text fw={500}>{current.title}</Text>
          <Code block>{current.source_path}</Code>

          {current.error && (
            <Text size="sm" c="red">
              {current.error}
            </Text>
          )}

          <Divider />

          <ActivityLog
            entries={current.log}
            empty="Nothing logged yet. The worker has not started this import."
          />

          <Divider />

          <Text size="xs" c="dimmed">
            {current.id} · queued {formatTimestamp(current.created_at)}
          </Text>
        </Stack>
      )}
    </Drawer>
  );
}
