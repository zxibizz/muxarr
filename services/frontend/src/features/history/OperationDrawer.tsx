import {
  Alert,
  Anchor,
  Badge,
  Divider,
  Drawer,
  Group,
  SimpleGrid,
  Stack,
  Tabs,
  Text,
  Title,
} from '@mantine/core';
import { IconExternalLink, IconInfoCircle, IconListCheck, IconStack2 } from '@tabler/icons-react';
import type { ArrContext, Operation } from '../../api/types';
import { AppBadge } from '../../components/AppBadge';
import { EmptyState } from '../../components/EmptyState';
import { CopyPath, KeyValue } from '../../components/KeyValue';
import { StatusBadge } from '../../components/StatusBadge';
import {
  displayName,
  formatBytes,
  formatDuration,
  formatSizeDelta,
  formatTimestamp,
} from '../../lib/format';
import { ActivityLog } from '../activity/ActivityLog';
import { EmbeddedTracks, PassedOverTracks, RemovedTracks } from './TrackTables';

function Overview({ operation }: { operation: Operation }) {
  const delta = formatSizeDelta(operation.source_bytes, operation.output_bytes);
  return (
    <Stack gap="lg">
      <SimpleGrid cols={{ base: 2, sm: 3 }} spacing="lg" verticalSpacing="md">
        <KeyValue label="Took">{formatDuration(operation.duration_ms)}</KeyValue>
        <KeyValue label="Transfer mode">{operation.transfer_mode || '—'}</KeyValue>
        <KeyValue label="Recorded">{formatTimestamp(operation.created_at)}</KeyValue>
        <KeyValue label="Source size">{formatBytes(operation.source_bytes)}</KeyValue>
        <KeyValue label="Output size">
          {formatBytes(operation.output_bytes)}
          {operation.output_bytes !== null && delta && (
            <Text span size="xs" c="dimmed">
              {' '}
              ({delta})
            </Text>
          )}
        </KeyValue>
        {operation.season !== null && (
          <KeyValue label="Episode">
            Season {operation.season}
            {operation.episodes.length > 0 && ` · episode ${operation.episodes.join(', ')}`}
          </KeyValue>
        )}
        {operation.arr && <ArrDetails app={operation.app} arr={operation.arr} />}
      </SimpleGrid>

      <Divider />

      <Stack gap="md">
        <CopyPath label="Source" path={operation.source_path} />
        <CopyPath label="Destination requested by *arr" path={operation.destination_path} />
        {operation.media_file && <CopyPath label="File Muxarr produced" path={operation.media_file} />}
      </Stack>
    </Stack>
  );
}

function ArrDetails({ app, arr }: { app: Operation['app']; arr: ArrContext }) {
  const name = app === 'radarr' ? 'Radarr' : 'Sonarr';
  const title = arr.year ? `${arr.title} (${arr.year})` : arr.title;
  return (
    <>
      {arr.title && (
        <KeyValue label={`In ${arr.instance || name}`}>
          {arr.link ? (
            <Anchor href={arr.link} target="_blank" rel="noopener noreferrer" size="sm">
              {title} <IconExternalLink size={12} style={{ verticalAlign: '-1px' }} />
            </Anchor>
          ) : (
            title
          )}
        </KeyValue>
      )}
      <KeyValue label="Original language">{arr.original_language ?? '—'}</KeyValue>
      <KeyValue label="Tags">{arr.tags.length > 0 ? arr.tags.join(', ') : '—'}</KeyValue>
    </>
  );
}

function Tracks({ operation }: { operation: Operation }) {
  const { added_tracks: added, rejected_tracks: rejected, removed_tracks: removed } = operation;
  if (added.length + rejected.length + removed.length === 0) {
    return <EmptyState icon={IconStack2} title="No tracks were considered" />;
  }
  return (
    <Stack gap="xl">
      {added.length > 0 && <EmbeddedTracks tracks={added} />}
      {removed.length > 0 && <RemovedTracks tracks={removed} />}
      {rejected.length > 0 && <PassedOverTracks tracks={rejected} />}
    </Stack>
  );
}

interface Props {
  operation: Operation | null;
  onClose: () => void;
}

export function OperationDrawer({ operation, onClose }: Props) {
  return (
    <Drawer
      opened={operation !== null}
      onClose={onClose}
      size="xl"
      padding="xl"
      title={
        operation && (
          <Group gap="xs">
            <StatusBadge status={operation.move_status} />
            <AppBadge app={operation.app} />
            {operation.dry_run && <Badge color="yellow">dry run</Badge>}
          </Group>
        )
      }
    >
      {operation && (
        <Stack gap="lg">
          <Stack gap={4}>
            <Title order={2} style={{ wordBreak: 'break-word' }}>
              {displayName(operation)}
            </Title>
            <Text size="sm" c="dimmed" style={{ wordBreak: 'break-all' }}>
              {operation.title}
            </Text>
          </Stack>

          <Alert
            variant="outline"
            color={operation.move_status === 'DeferMove' ? 'gray' : 'teal'}
            icon={<IconInfoCircle size={18} />}
          >
            {operation.reason}
          </Alert>

          <Tabs defaultValue="overview" keepMounted={false}>
            <Tabs.List>
              <Tabs.Tab value="overview">Overview</Tabs.Tab>
              <Tabs.Tab
                value="tracks"
                rightSection={
                  <Badge size="xs" color="gray" circle>
                    {operation.added_tracks.length}
                  </Badge>
                }
              >
                Tracks
              </Tabs.Tab>
              <Tabs.Tab value="activity" leftSection={<IconListCheck size={14} />}>
                What happened
              </Tabs.Tab>
            </Tabs.List>

            <Tabs.Panel value="overview" pt="lg">
              <Overview operation={operation} />
            </Tabs.Panel>
            <Tabs.Panel value="tracks" pt="lg">
              <Tracks operation={operation} />
            </Tabs.Panel>
            <Tabs.Panel value="activity" pt="lg">
              <ActivityLog entries={operation.log} />
            </Tabs.Panel>
          </Tabs>

          <Text size="xs" c="dimmed">
            Operation #{operation.id}
          </Text>
        </Stack>
      )}
    </Drawer>
  );
}
