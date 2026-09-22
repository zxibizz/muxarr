"""Turn a release folder into a question a language model can answer.

Only *names* leave the machine: filenames relative to the release folder, their
sizes, and the target video's own filename. Never file contents, never an absolute
path, and so never anything about the library layout above the release folder.

The candidate list doubles as an allow-list. Whatever the model replies with is
looked up in :attr:`DiscoveryPrompt.index`, so it can only ever select and label
files the filesystem already enumerated -- it cannot introduce a path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.core.logging import get_logger
from src.domain.codecs import VIDEO_EXTENSIONS
from src.domain.enums import LogComponent
from src.domain.naming import EpisodeRef
from src.infrastructure.filesystem.track_discovery import classify, index_candidates

log = get_logger(LogComponent.INFRA_AI)

# Enough for the model to see it is looking at a season pack, without paying for
# the whole listing twice.
MAX_SIBLING_VIDEOS = 40

SYSTEM_PROMPT = """\
You match external audio and subtitle files to one specific video file from a \
scene release folder.

You are given the target video's filename, the other video filenames sitting \
beside it, and a list of candidate sidecar files with paths relative to the \
release folder.

Reply with JSON only, in exactly this shape:

{"tracks": [{"file": "<path copied verbatim from the candidate list>",
             "kind": "audio" | "subtitles",
             "language": "<ISO 639-2/B code, or \\"und\\">",
             "title": "<short human-readable label, or null>",
             "forced": true | false,
             "hearing_impaired": true | false,
             "variant": "<dub or release group tag, or null>"}]}

Rules:
- Include only files belonging to THIS video. When the folder holds several \
episodes, a sidecar belongs to the video whose season/episode marker it shares.
- Copy "file" character for character from the candidate list. Never invent, \
complete or correct a path. Omit anything you are unsure about.
- Prefer "und" to a guess. An unknown language is a correct answer; a wrong one \
gets written permanently into the user's library.
- "variant" only distinguishes two dubs of the SAME language, usually a studio or \
group name, often taken from the containing folder. Otherwise null.
- "forced" marks tracks covering only foreign dialogue or on-screen signs.
- "hearing_impaired" marks SDH/CC subtitles.
- A language folder name applies to every file inside it.
- Return an empty list when nothing belongs to this video.
"""


@dataclass(frozen=True, slots=True)
class DiscoveryPrompt:
    system: str
    user: str
    # Relative POSIX path -> the real absolute path. The only way back to a Path.
    index: dict[str, Path]


def build(
    video_path: Path,
    *,
    episode: EpisodeRef | None = None,
    max_entries: int = 200,
) -> DiscoveryPrompt | None:
    """Describe the folder around ``video_path``, or ``None`` if not worth asking."""
    root = video_path.parent
    if not root.is_dir():
        return None

    index: dict[str, Path] = {}
    candidates: list[dict[str, object]] = []
    for path, _context in sorted(index_candidates(root)):
        if path == video_path or classify(path) is None:
            continue
        relative = path.relative_to(root).as_posix()
        index[relative] = path
        candidates.append({"file": relative, "bytes": _size_of(path)})

    if not candidates:
        return None
    if len(candidates) > max_entries:
        log.info(
            "skipping ai discovery: too many candidates",
            count=len(candidates),
            max_entries=max_entries,
        )
        return None

    payload: dict[str, object] = {
        "video": video_path.name,
        "other_videos_in_folder": _sibling_videos(root, video_path),
        "candidates": candidates,
    }
    if episode is not None:
        payload["episode"] = {"season": episode.season, "episodes": list(episode.episodes)}

    return DiscoveryPrompt(
        system=SYSTEM_PROMPT,
        user=json.dumps(payload, ensure_ascii=False, indent=1),
        index=index,
    )


def _sibling_videos(root: Path, video_path: Path) -> list[str]:
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return []
    names = [
        p.name
        for p in entries
        if p.is_file() and p != video_path and p.suffix.lower() in VIDEO_EXTENSIONS
    ]
    return names[:MAX_SIBLING_VIDEOS]


def _size_of(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None
