"""A few lines of a text subtitle's dialogue, so a model can read which language it is in.

Numbering, timing and markup are stripped: only what a viewer would read is sent.
"""

from __future__ import annotations

import codecs
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from charset_normalizer import from_bytes

from src.domain.codecs import TEXT_SUBTITLE_SUFFIXES

MAX_READ_BYTES = 1 << 20
MAX_EXCERPT_CHARS = 300

_MARKUP = re.compile(r"<[^>]*>|\{[^}]*\}")
_ASS_BREAK = re.compile(r"\\[Nnh]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_BOMS = (
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)


# exact: a BOM, UTF-8 or the configured charset. guessed: a statistical guess at the
# code page. unknown: nothing fitted and Latin-1 was the last resort, so likely mojibake.
Decoding = Literal["exact", "guessed", "unknown"]


@dataclass(frozen=True, slots=True)
class Excerpt:
    text: str
    decoding: Decoding = "exact"


def excerpt(path: Path, *, charset: str | None = None) -> Excerpt | None:
    suffix = path.suffix.lower()
    if suffix not in TEXT_SUBTITLE_SUFFIXES:
        return None
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_READ_BYTES)
    except OSError:
        return None

    text, decoding = _decode(raw, charset)
    lines = _ass_dialogue(text) if suffix in (".ass", ".ssa") else _cue_dialogue(text)
    sample = _from_the_middle(lines)
    return Excerpt(sample, decoding) if sample else None


def _decode(raw: bytes, charset: str | None) -> tuple[str, Decoding]:
    for bom, encoding in _BOMS:
        if raw.startswith(bom):
            return raw.decode(encoding, errors="replace"), "exact"

    for encoding in ("utf-8", charset or ""):
        if not encoding:
            continue
        try:
            # Incremental, so a multi-byte character cut off by the read limit is not an error.
            return codecs.getincrementaldecoder(encoding)().decode(raw, final=False), "exact"
        except (LookupError, UnicodeDecodeError):
            continue

    # Models cannot reliably read Cyrillic through Latin-1 mojibake: left to it, the
    # same Windows-1251 file comes back "rus" on one episode and "und" on the next.
    if (best := from_bytes(raw).best()) is not None:
        return str(best), "guessed"
    return raw.decode("latin-1"), "unknown"


def _cue_dialogue(text: str) -> list[str]:
    """SRT and WebVTT: the lines after each cue's timing line."""
    lines: list[str] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n")):
        rows = block.strip().split("\n")
        timing = next((i for i, row in enumerate(rows) if "-->" in row), None)
        if timing is None:
            # WEBVTT header, NOTE, STYLE, REGION: nothing a viewer reads.
            continue
        lines += [clean for row in rows[timing + 1 :] if (clean := _clean(row))]
    return lines


def _ass_dialogue(text: str) -> list[str]:
    lines: list[str] = []
    for row in text.splitlines():
        if not row.startswith("Dialogue:"):
            continue
        fields = row.split(",", 9)
        if len(fields) == 10 and (clean := _clean(_ASS_BREAK.sub(" ", fields[9]))):
            lines.append(clean)
    return lines


def _clean(row: str) -> str:
    text = " ".join(_CONTROL.sub(" ", _MARKUP.sub("", row)).split())
    return text if any(c.isalpha() for c in text) else ""


def _from_the_middle(lines: list[str]) -> str:
    # Credits and group ads sit at either end, often in another language.
    picked: list[str] = []
    length = 0
    for line in lines[len(lines) // 3 :]:
        picked.append(line)
        length += len(line) + 3
        if length >= MAX_EXCERPT_CHARS:
            break
    return " / ".join(picked)[:MAX_EXCERPT_CHARS]
