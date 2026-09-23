import { Badge, Group, Tooltip } from '@mantine/core';
import { IconBadgeCc, IconMovie, IconSparkles, IconVolume } from '@tabler/icons-react';
import type { AddedTrack, TrackKind } from '../api/types';
import { explainTrack } from '../lib/format';

const KINDS: Record<TrackKind, { color: string; icon: typeof IconVolume; name: string }> = {
  audio: { color: 'grape', icon: IconVolume, name: 'audio' },
  subtitles: { color: 'cyan', icon: IconBadgeCc, name: 'subtitles' },
  video: { color: 'gray', icon: IconMovie, name: 'video' },
};

export function TrackChip({ track }: { track: AddedTrack }) {
  const { color, icon: Icon, name } = KINDS[track.kind];
  // The release group or folder name is in the tooltip; on the chip it is just noise.
  const flags = [track.forced && 'forced', track.hearing_impaired && 'SDH'].filter(Boolean);

  return (
    <Tooltip label={explainTrack(track)} multiline maw={360}>
      <Badge
        color={color}
        tt="none"
        fw={600}
        leftSection={<Icon size={12} stroke={2} />}
        rightSection={track.source === 'ai' ? <IconSparkles size={11} /> : undefined}
        aria-label={`${name}: ${track.label}`}
      >
        {track.language.toUpperCase()}
        {flags.length > 0 && ` · ${flags.join(', ')}`}
      </Badge>
    </Tooltip>
  );
}

export function TrackChips({ tracks, max = 4 }: { tracks: AddedTrack[]; max?: number }) {
  const shown = tracks.slice(0, max);
  const hidden = tracks.length - shown.length;
  return (
    <Group gap={4} wrap="wrap">
      {shown.map((track) => (
        <TrackChip key={`${track.kind}:${track.file}:${track.label}`} track={track} />
      ))}
      {hidden > 0 && (
        <Badge color="gray" variant="outline" tt="none">
          +{hidden}
        </Badge>
      )}
    </Group>
  );
}
