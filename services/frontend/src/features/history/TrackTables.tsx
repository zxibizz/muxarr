import { Badge, Group, Stack, Table, Text, ThemeIcon, Title, Tooltip } from '@mantine/core';
import { IconBadgeCc, IconMovie, IconSparkles, IconVolume } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import type { AddedTrack, RejectedTrack, RemovedTrack, TrackKind } from '../../api/types';
import { REJECT_LABELS, rejectColour, trackFlags } from '../../lib/format';

const KIND_ICON: Record<TrackKind, typeof IconVolume> = {
  audio: IconVolume,
  subtitles: IconBadgeCc,
  video: IconMovie,
};

function KindIcon({ kind }: { kind: TrackKind }) {
  const Icon = KIND_ICON[kind];
  return (
    <Tooltip label={kind}>
      <ThemeIcon size={24} variant="light" color={kind === 'audio' ? 'grape' : 'cyan'} radius="sm">
        <Icon size={14} />
      </ThemeIcon>
    </Tooltip>
  );
}

function Section({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  return (
    <Stack gap="xs">
      <Group gap="xs">
        <Title order={3}>{title}</Title>
        <Badge color="gray" variant="light" circle>
          {count}
        </Badge>
      </Group>
      {children}
    </Stack>
  );
}

function Mono({ children }: { children: ReactNode }) {
  return (
    <Text size="xs" c="dimmed" ff="monospace" style={{ wordBreak: 'break-all' }}>
      {children}
    </Text>
  );
}

export function EmbeddedTracks({ tracks }: { tracks: AddedTrack[] }) {
  return (
    <Section title="Tracks embedded" count={tracks.length}>
      <Table verticalSpacing="xs" withRowBorders={false}>
        <Table.Tbody>
          {tracks.map((track) => (
            <Table.Tr key={`${track.kind}:${track.file}:${track.label}`}>
              <Table.Td w={36}>
                <KindIcon kind={track.kind} />
              </Table.Td>
              <Table.Td>
                <Group gap={6}>
                  <Text size="sm" fw={500}>
                    {track.label}
                  </Text>
                  <Badge size="xs" color="gray" variant="outline">
                    {track.language}
                  </Badge>
                  {trackFlags(track).map((flag) => (
                    <Badge key={flag} size="xs" color="gray">
                      {flag}
                    </Badge>
                  ))}
                </Group>
                <Mono>{track.file}</Mono>
              </Table.Td>
              <Table.Td w={110} ta="right">
                {track.source === 'ai' ? (
                  <Tooltip label="Identified by the AI provider">
                    <Badge color="brand" leftSection={<IconSparkles size={11} />} tt="none">
                      by AI
                    </Badge>
                  </Tooltip>
                ) : (
                  <Text size="xs" c="dimmed">
                    {track.source === 'tags' ? 'by file tags' : 'by filename'}
                  </Text>
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Section>
  );
}

export function PassedOverTracks({ tracks }: { tracks: RejectedTrack[] }) {
  return (
    <Section title="Sidecars passed over" count={tracks.length}>
      <Table verticalSpacing="xs" withRowBorders={false}>
        <Table.Tbody>
          {tracks.map((rejected) => (
            <Table.Tr key={`${rejected.track}:${rejected.reason}`}>
              <Table.Td w={36}>
                <KindIcon kind={rejected.kind} />
              </Table.Td>
              <Table.Td>
                <Text size="sm" fw={500} style={{ wordBreak: 'break-all' }}>
                  {rejected.track}
                </Text>
                <Text size="xs" c="dimmed">
                  {rejected.reason}
                </Text>
              </Table.Td>
              <Table.Td w={140} ta="right">
                {rejected.code && (
                  <Badge color={rejectColour(rejected.code)} tt="none">
                    {REJECT_LABELS[rejected.code]}
                  </Badge>
                )}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Section>
  );
}

export function RemovedTracks({ tracks }: { tracks: RemovedTrack[] }) {
  return (
    <Section title="Removed from source" count={tracks.length}>
      <Table verticalSpacing="xs" withRowBorders={false}>
        <Table.Tbody>
          {tracks.map((removed) => (
            <Table.Tr key={`${removed.kind}:${removed.index}`}>
              <Table.Td w={36}>
                <KindIcon kind={removed.kind} />
              </Table.Td>
              <Table.Td>
                <Group gap={6}>
                  <Text size="sm" fw={500}>
                    {removed.name ?? removed.language}
                  </Text>
                  <Badge size="xs" color="gray" variant="outline">
                    {removed.language}
                  </Badge>
                  {removed.codec && (
                    <Badge size="xs" color="gray">
                      {removed.codec}
                    </Badge>
                  )}
                  {removed.forced && (
                    <Badge size="xs" color="gray">
                      forced
                    </Badge>
                  )}
                </Group>
                <Text size="xs" c="dimmed">
                  track {removed.index}, {removed.reason}
                </Text>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Section>
  );
}
