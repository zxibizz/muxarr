import { Badge, Card, Group, Loader, Stack, Text, UnstyledButton } from '@mantine/core';
import { IconChevronRight } from '@tabler/icons-react';
import { useUnsettledJobs } from '../../api/queries';
import type { Job } from '../../api/types';
import { AppBadge } from '../../components/AppBadge';
import { formatRelative } from '../../lib/format';
import classes from './rows.module.css';

function JobStateBadge({ job }: { job: Job }) {
  if (job.state === 'running') {
    return (
      <Badge color="brand" leftSection={<Loader size={10} color="brand" type="dots" />}>
        running
      </Badge>
    );
  }
  return <Badge color={job.state === 'failed' ? 'red' : 'gray'}>{job.state}</Badge>;
}

export function ActiveJobs({ onSelect }: { onSelect: (jobId: string) => void }) {
  const { data: jobs = [] } = useUnsettledJobs();
  if (jobs.length === 0) return null;

  return (
    <Card padding={0}>
      <Group justify="space-between" px="lg" py="sm">
        <Group gap="xs">
          <Text fw={600}>In flight</Text>
          <Badge color="brand" variant="filled" circle>
            {jobs.length}
          </Badge>
        </Group>
        <Text size="xs" c="dimmed">
          Imports that have not produced a history entry yet
        </Text>
      </Group>
      <Stack gap={0}>
        {jobs.map((job) => (
          <UnstyledButton key={job.id} className={classes.row} onClick={() => onSelect(job.id)}>
            <Group wrap="nowrap" gap="md" px="lg" py="sm">
              <JobStateBadge job={job} />
              <Stack gap={0} style={{ flex: 1, minWidth: 0 }}>
                <Text size="sm" fw={500} truncate>
                  {job.title}
                </Text>
                {job.error && (
                  <Text size="xs" c="red" truncate>
                    {job.error}
                  </Text>
                )}
              </Stack>
              <AppBadge app={job.app} />
              <Text size="xs" c="dimmed" w={64} ta="right">
                {formatRelative(job.created_at)}
              </Text>
              <IconChevronRight size={16} color="var(--mantine-color-dimmed)" />
            </Group>
          </UnstyledButton>
        ))}
      </Stack>
    </Card>
  );
}
