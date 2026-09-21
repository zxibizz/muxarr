"""Closed vocabularies shared across the layers.

Kept as ``Literal`` aliases rather than ``StrEnum``: every value crosses a JSON
or argv boundary as a bare string, and mypy already rejects a typo in either.
"""

from __future__ import annotations

from typing import Literal

TrackKind = Literal["video", "audio", "subtitles"]

# ISO 639-2 "undetermined"; mkvmerge's own default for an untagged track.
UNDETERMINED = "und"

DedupeMode = Literal["off", "language", "language_codec"]

# The three verdicts Radarr/Sonarr understand on an import script's stdout.
MoveStatus = Literal["DeferMove", "MoveComplete", "RenameRequested"]

App = Literal["radarr", "sonarr"]
