import { Badge, Center, Group, Loader, Stack, Table, Text, Tooltip } from '@mantine/core';
import { formatDuration, formatRelative, formatTimestamp, shortenPath } from '../format';
import type { Operation } from '../types';
import { StatusBadge } from './StatusBadge';

interface Props {
  operations: Operation[];
  loading: boolean;
  onSelect: (operation: Operation) => void;
}

export function HistoryTable({ operations, loading, onSelect }: Props) {
  if (loading && operations.length === 0) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    );
  }

  if (operations.length === 0) {
    return (
      <Stack align="center" py="xl" gap="xs">
        <Text fw={600}>No operations yet</Text>
        <Text size="sm" c="dimmed" ta="center" maw={460}>
          muxarr records every import Radarr or Sonarr hands it, including the ones it
          skipped. Import something and it will show up here.
        </Text>
      </Stack>
    );
  }

  return (
    <Table.ScrollContainer minWidth={860}>
      <Table highlightOnHover verticalSpacing="sm">
        <Table.Thead>
          <Table.Tr>
            <Table.Th w={110}>When</Table.Th>
            <Table.Th w={100}>Result</Table.Th>
            <Table.Th>Title</Table.Th>
            <Table.Th w={90}>Source</Table.Th>
            <Table.Th>Tracks added</Table.Th>
            <Table.Th w={90}>Took</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {operations.map((operation) => (
            <Table.Tr
              key={operation.id}
              onClick={() => onSelect(operation)}
              style={{ cursor: 'pointer' }}
            >
              <Table.Td>
                <Tooltip label={formatTimestamp(operation.created_at)} withArrow>
                  <Text size="sm" c="dimmed">
                    {formatRelative(operation.created_at)}
                  </Text>
                </Tooltip>
              </Table.Td>
              <Table.Td>
                <StatusBadge status={operation.move_status} />
              </Table.Td>
              <Table.Td>
                <Text size="sm" fw={500} lineClamp={1}>
                  {operation.title}
                </Text>
                <Text size="xs" c="dimmed" lineClamp={1}>
                  {operation.reason}
                </Text>
              </Table.Td>
              <Table.Td>
                <Badge variant="outline" size="sm">
                  {operation.app}
                </Badge>
              </Table.Td>
              <Table.Td>
                {operation.added_tracks.length === 0 ? (
                  <Text size="sm" c="dimmed">
                    —
                  </Text>
                ) : (
                  <Group gap={4} wrap="wrap">
                    {operation.added_tracks.map((track) => (
                      <Badge key={track} size="sm" variant="light" color="teal">
                        {track}
                      </Badge>
                    ))}
                  </Group>
                )}
              </Table.Td>
              <Table.Td>
                <Tooltip label={shortenPath(operation.source_path)} withArrow>
                  <Text size="sm" c="dimmed">
                    {formatDuration(operation.duration_ms)}
                  </Text>
                </Tooltip>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
