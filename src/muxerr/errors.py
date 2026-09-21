"""Exception hierarchy.

Everything raised by the core inherits from :class:`MuxerrError` so the import
pipeline can catch exactly one type and degrade to a no-op instead of failing an
Radarr/Sonarr import.
"""

from __future__ import annotations


class MuxerrError(Exception):
    """Base class for every expected failure."""


class ToolNotFoundError(MuxerrError):
    """A required external binary (mkvmerge/ffprobe/ffmpeg) is missing."""


class ProbeError(MuxerrError):
    """A media file could not be inspected."""


class MuxError(MuxerrError):
    """mkvmerge/ffmpeg failed, or produced output that failed verification."""


class PlacementError(MuxerrError):
    """The muxed result could not be put at its final path."""


class InsufficientSpaceError(MuxerrError):
    """Not enough free space on the destination filesystem to hold the result."""


class PathNotAllowedError(MuxerrError):
    """A path resolved outside its permitted root."""
