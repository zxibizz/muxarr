"""Exception hierarchy.

Everything raised by the core inherits from :class:`MuxarrError` so the import
pipeline can catch exactly one type and degrade to a no-op instead of failing an
Radarr/Sonarr import.
"""

from __future__ import annotations


class MuxarrError(Exception):
    """Base class for every expected failure."""


class ToolNotFoundError(MuxarrError):
    """A required external binary (mkvmerge/ffprobe/ffmpeg) is missing."""


class ProbeError(MuxarrError):
    """A media file could not be inspected."""


class MuxError(MuxarrError):
    """mkvmerge/ffmpeg failed, or produced output that failed verification."""


class PlacementError(MuxarrError):
    """The muxed result could not be put at its final path."""


class InsufficientSpaceError(MuxarrError):
    """Not enough free space on the destination filesystem to hold the result."""


class PathNotAllowedError(MuxarrError):
    """A path resolved outside its permitted root."""


class AiError(MuxarrError):
    """The AI provider could not be reached, or did not answer usefully."""
