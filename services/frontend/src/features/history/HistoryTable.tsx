import { Group, Skeleton, Stack, Table, Text, Tooltip } from '@mantine/core';
import { IconInbox } from '@tabler/icons-react';
import type { KeyboardEvent } from 'react';
import type { Operation } from '../../api/types';
import { AppBadge } from '../../components/AppBadge';
import { EmptyState } from '../../components/EmptyState';
import { StatusBadge } from '../../components/StatusBadge';
import { TrackChips } from '../../components/TrackChip';
import { displayName, formatDuration, formatRelative, formatTimestamp } from '../../lib/format';
import classes from './rows.module.css';

interface Props {
  operations: Operation[];
  loading: boolean;
  filtered: boolean;
  onSelect: (operation: Operation) => void;
}

function SkeletonRows() {
  return Array.from({ length: 6 }, (_, index) => (
    <Table.Tr key={index}>
      <Table.Td>
        <Skeleton height={20} width={72} />
      </Table.Td>
      <Table.Td>
        <Skeleton height={14} width="60%" mb={6} />
        <Skeleton height={10} width="40%" />
      </Table.Td>
      <Table.Td>
        <Skeleton height={20} width={120} />
      </Table.Td>
      <Table.Td visibleFrom="md">
        <Skeleton height={20} width={64} />
      </Table.Td>
      <Table.Td visibleFrom="lg">
        <Skeleton height={14} width={56} />
      </Table.Td>
      <Table.Td visibleFrom="xl">
        <Skeleton height={14} width={40} ml="auto" />
      </Table.Td>
    </Table.Tr>
  ));
}

export function HistoryTable({ operations, loading, filtered, onSelect }: Props) {
  if (!loading && operations.length === 0) {
    return filtered ? (
      <EmptyState icon={IconInbox} title="Nothing matches these filters" />
    ) : (
      <EmptyState icon={IconInbox} title="No imports yet">
        muxarr records every import Radarr or Sonarr hands it, including the ones it left alone.
        Import something and it shows up here.
      </EmptyState>
    );
  }

  const activate = (event: KeyboardEvent, operation: Operation) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onSelect(operation);
    }
  };

  return (
    <Table.ScrollContainer minWidth={640}>
      <Table highlightOnHover layout="fixed">
        <Table.Thead>
          <Table.Tr>
            <Table.Th w={124}>Result</Table.Th>
            <Table.Th>Title</Table.Th>
            <Table.Th w={260}>Tracks added</Table.Th>
            <Table.Th w={116} visibleFrom="md">
              Source
            </Table.Th>
            <Table.Th w={96} visibleFrom="lg">
              When
            </Table.Th>
            <Table.Th w={80} ta="right" visibleFrom="xl">
              Took
            </Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {loading && operations.length === 0 ? (
            <SkeletonRows />
          ) : (
            operations.map((operation) => (
              <Table.Tr
                key={operation.id}
                className={classes.clickable}
                tabIndex={0}
                aria-label={`Open ${displayName(operation)}`}
                onClick={() => onSelect(operation)}
                onKeyDown={(event) => activate(event, operation)}
              >
                <Table.Td>
                  <StatusBadge status={operation.move_status} />
                </Table.Td>
                <Table.Td>
                  <Stack gap={2}>
                    <Text size="sm" fw={500} lineClamp={1}>
                      {displayName(operation)}
                    </Text>
                    <Text size="xs" c="dimmed" lineClamp={1}>
                      {operation.move_status === 'DeferMove' ? operation.reason : operation.title}
                    </Text>
                  </Stack>
                </Table.Td>
                <Table.Td>
                  {operation.added_tracks.length === 0 ? (
                    <Text size="sm" c="dimmed">
                      —
                    </Text>
                  ) : (
                    <TrackChips tracks={operation.added_tracks} max={3} />
                  )}
                </Table.Td>
                <Table.Td visibleFrom="md">
                  <Group gap={4}>
                    <AppBadge app={operation.app} />
                  </Group>
                </Table.Td>
                <Table.Td visibleFrom="lg">
                  <Tooltip label={formatTimestamp(operation.created_at)}>
                    <Text size="sm" c="dimmed">
                      {formatRelative(operation.created_at)}
                    </Text>
                  </Tooltip>
                </Table.Td>
                <Table.Td ta="right" visibleFrom="xl">
                  <Text
                    size="sm"
                    c="dimmed"
                    style={{ fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}
                  >
                    {formatDuration(operation.duration_ms)}
                  </Text>
                </Table.Td>
              </Table.Tr>
            ))
          )}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
