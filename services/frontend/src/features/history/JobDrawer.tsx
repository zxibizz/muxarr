import { Alert, Badge, Drawer, Group, Loader, Stack, Text, Title } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { isTerminal, useJob } from '../../api/queries';
import { AppBadge } from '../../components/AppBadge';
import { CopyPath } from '../../components/KeyValue';
import { formatTimestamp } from '../../lib/format';
import { ActivityLog } from '../activity/ActivityLog';
import type { JobState } from '../../api/types';

const HEADINGS: Record<JobState, string> = {
  pending: 'Waiting for the worker',
  running: 'Import in progress',
  succeeded: 'Import finished',
  failed: 'Import failed',
};

interface Props {
  jobId: string | null;
  onClose: () => void;
}

export function JobDrawer({ jobId, onClose }: Props) {
  const { data: job } = useJob(jobId);
  const live = job !== undefined && !isTerminal(job);

  return (
    <Drawer
      opened={jobId !== null}
      onClose={onClose}
      size="xl"
      padding="xl"
      title={
        job && (
          <Group gap="xs">
            <Badge
              color={job.state === 'failed' ? 'red' : 'brand'}
              leftSection={live ? <Loader size={10} type="dots" color="brand" /> : undefined}
            >
              {job.state}
            </Badge>
            <AppBadge app={job.app} />
            {job.dry_run && <Badge color="yellow">dry run</Badge>}
          </Group>
        )
      }
    >
      {job ? (
        <Stack gap="lg">
          <Stack gap={4}>
            <Title order={2} style={{ wordBreak: 'break-word' }}>
              {HEADINGS[job.state]}
            </Title>
            <Text size="sm" c="dimmed" style={{ wordBreak: 'break-all' }}>
              {job.title}
            </Text>
          </Stack>

          {job.error && (
            <Alert color="red" icon={<IconAlertTriangle size={18} />} title="The import failed">
              {job.error}
            </Alert>
          )}

          <CopyPath label="Source" path={job.source_path} />

          <Stack gap="xs">
            <Group justify="space-between">
              <Title order={3}>What is happening</Title>
              {live && (
                <Text size="xs" c="dimmed">
                  Live · refreshes every 2 seconds
                </Text>
              )}
            </Group>
            <ActivityLog
              entries={job.log}
              empty="Nothing logged yet. The worker has not started this import."
            />
          </Stack>

          <Text size="xs" c="dimmed">
            Job {job.id} · queued {formatTimestamp(job.created_at)}
          </Text>
        </Stack>
      ) : (
        <Group justify="center" py="xl">
          <Loader />
        </Group>
      )}
    </Drawer>
  );
}
