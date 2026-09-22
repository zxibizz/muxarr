import { Badge, Card, Group, Stack, Table, Text, Title } from '@mantine/core';
import { formatRelative } from '../format';
import type { Job, JobState } from '../types';

const STATE_COLOURS: Record<JobState, string> = {
  pending: 'gray',
  running: 'blue',
  succeeded: 'teal',
  failed: 'red',
};

interface Props {
  jobs: Job[];
  onSelect: (job: Job) => void;
}

export function ActiveJobs({ jobs, onSelect }: Props) {
  if (jobs.length === 0) return null;

  return (
    <Card withBorder padding="md">
      <Stack gap="xs">
        <Group justify="space-between">
          <Title order={5}>In flight</Title>
          <Text size="xs" c="dimmed">
            Imports that have not produced a history entry yet
          </Text>
        </Group>
        <Table highlightOnHover verticalSpacing="xs">
          <Table.Tbody>
            {jobs.map((job) => (
              <Table.Tr
                key={job.id}
                onClick={() => onSelect(job)}
                style={{ cursor: 'pointer' }}
              >
                <Table.Td w={100}>
                  <Badge size="sm" color={STATE_COLOURS[job.state]} variant="light">
                    {job.state}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" lineClamp={1}>
                    {job.title}
                  </Text>
                  {job.error && (
                    <Text size="xs" c="red" lineClamp={1}>
                      {job.error}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td w={90}>
                  <Text size="xs" c="dimmed">
                    {formatRelative(job.created_at)}
                  </Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Stack>
    </Card>
  );
}
