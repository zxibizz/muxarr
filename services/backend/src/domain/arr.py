"""What Radarr/Sonarr know about an import, beyond the two paths.

The shim forwards it from the import script's environment. All of it is optional:
an import without it (an older shim, a hand-made request) behaves exactly as
before, and every rule that reads it degrades to its no-information answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from src.domain.enums import App


@dataclass(frozen=True, slots=True)
class ArrContext:
    # Settings > General > Instance Name, which tells Radarr from Radarr 4K.
    instance: str = ""
    # Settings > General > Application URL; empty unless the user set one.
    url: str = ""
    title: str = ""
    year: int | None = None
    # The item's route in the *arr UI: a TMDb id in Radarr, a title slug in Sonarr.
    slug: str = ""
    # Canonical ISO 639-2/B, or None when *arr did not say.
    original_language: str | None = None
    # Lower-cased: *arr tag labels are lower-case already, but a comparison must not care.
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance": self.instance,
            "url": self.url,
            "title": self.title,
            "year": self.year,
            "slug": self.slug,
            "original_language": self.original_language,
            "tags": list(self.tags),
        }

    @classmethod
    def from_stored(cls, data: Mapping[str, Any] | None) -> ArrContext | None:
        if not data:
            return None
        year = data.get("year")
        return cls(
            instance=str(data.get("instance") or ""),
            url=str(data.get("url") or ""),
            title=str(data.get("title") or ""),
            year=int(year) if isinstance(year, int) else None,
            slug=str(data.get("slug") or ""),
            original_language=data.get("original_language") or None,
            tags=tuple(str(t) for t in data.get("tags") or ()),
        )


def item_url(app: App, context: ArrContext | None) -> str | None:
    """A link to the movie or series in *arr, when it told us enough to build one.

    The base URL came over HTTP and ends up in an href, so anything but http(s)
    is refused rather than rendered.
    """
    if context is None or not context.url or not context.slug:
        return None
    base = context.url.rstrip("/")
    if not base.lower().startswith(("http://", "https://")):
        return None
    section = "movie" if app == "radarr" else "series"
    return f"{base}/{section}/{quote(context.slug, safe='')}"
