import { Badge, Tooltip } from '@mantine/core';
import { explainTrack } from '../format';
import type { AddedTrack } from '../types';

export function TrackBadge({ track, size = 'sm' }: { track: AddedTrack; size?: string }) {
  return (
    <Tooltip label={explainTrack(track)} withArrow multiline maw={360}>
      <Badge
        size={size}
        color="teal"
        // The dot marks an AI-identified track without spending words on it.
        variant={track.source === 'ai' ? 'dot' : 'light'}
      >
        {track.kind}: {track.label}
      </Badge>
    </Tooltip>
  );
}
