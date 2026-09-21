import { Badge, Code, Divider, Drawer, Group, List, Stack, Text, Title } from '@mantine/core';
import { formatBytes, formatDuration, formatTimestamp } from '../format';
import type { Operation } from '../types';
import { StatusBadge } from './StatusBadge';

interface Props {
  operation: Operation | null;
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

export function OperationDetail({ operation, onClose }: Props) {
  return (
    <Drawer
      opened={operation !== null}
      onClose={onClose}
      position="right"
      size="lg"
      padding="lg"
      title={<Title order={4}>Operation detail</Title>}
    >
      {operation && (
        <Stack gap="md">
          <Group gap="xs">
            <StatusBadge status={operation.move_status} />
            <Badge variant="outline">{operation.app}</Badge>
            {operation.dry_run && <Badge color="yellow">dry run</Badge>}
          </Group>

          <Field label="Title">
            <Text fw={500}>{operation.title}</Text>
          </Field>

          <Field label="Why">
            <Text size="sm">{operation.reason}</Text>
          </Field>

          <Divider />

          <Field label="Source">
            <Code block>{operation.source_path}</Code>
          </Field>

          <Field label="Destination requested by *arr">
            <Code block>{operation.destination_path}</Code>
          </Field>

          {operation.media_file && (
            <Field label="File muxarr produced">
              <Code block>{operation.media_file}</Code>
            </Field>
          )}

          <Divider />

          <Group grow>
            <Field label="Transfer mode">
              <Text size="sm">{operation.transfer_mode || '—'}</Text>
            </Field>
            <Field label="Took">
              <Text size="sm">{formatDuration(operation.duration_ms)}</Text>
            </Field>
          </Group>

          <Group grow>
            <Field label="Source size">
              <Text size="sm">{formatBytes(operation.source_bytes)}</Text>
            </Field>
            <Field label="Output size">
              <Text size="sm">{formatBytes(operation.output_bytes)}</Text>
            </Field>
          </Group>

          {operation.season !== null && (
            <Field label="Episode">
              <Text size="sm">
                Season {operation.season}
                {operation.episodes.length > 0 &&
                  ` · episode ${operation.episodes.join(', ')}`}
              </Text>
            </Field>
          )}

          <Divider />

          <Field label={`Tracks embedded (${operation.added_tracks.length})`}>
            {operation.added_tracks.length === 0 ? (
              <Text size="sm" c="dimmed">
                None
              </Text>
            ) : (
              <Group gap={6} wrap="wrap">
                {operation.added_tracks.map((track) => (
                  <Badge key={track} variant="light" color="teal">
                    {track}
                  </Badge>
                ))}
              </Group>
            )}
          </Field>

          <Field label={`Sidecars passed over (${operation.rejected_tracks.length})`}>
            {operation.rejected_tracks.length === 0 ? (
              <Text size="sm" c="dimmed">
                None
              </Text>
            ) : (
              <List size="sm" spacing={4}>
                {operation.rejected_tracks.map((rejected) => (
                  <List.Item key={`${rejected.track}:${rejected.reason}`}>
                    <Text size="sm" span fw={500}>
                      {rejected.track}
                    </Text>
                    <Text size="sm" span c="dimmed">
                      {' '}
                      — {rejected.reason}
                    </Text>
                  </List.Item>
                ))}
              </List>
            )}
          </Field>

          <Divider />

          <Text size="xs" c="dimmed">
            #{operation.id} · {formatTimestamp(operation.created_at)}
          </Text>
        </Stack>
      )}
    </Drawer>
  );
}
