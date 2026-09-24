"""The *arr context of an import, on the wire in both directions."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.domain.arr import ArrContext, item_url
from src.domain.enums import App
from src.domain.language import normalise_language
from src.schemas.base import WireModel


class ArrPayload(BaseModel):
    """As the shim sends it: every value a string, straight from the environment.

    Lenient on purpose. A value that fails validation here would 422 the whole
    import and delay *arr for a minute of retries, over a detail that is only
    ever informational or an input to an optional rule.
    """

    instance: str = ""
    url: str = ""
    title: str = ""
    year: str = ""
    slug: str = ""
    original_language: str = ""
    # "|"-separated, as *arr joins them.
    tags: str = ""

    def to_context(self) -> ArrContext:
        year = self.year.strip()
        return ArrContext(
            instance=self.instance.strip(),
            url=self.url.strip(),
            title=self.title.strip(),
            # *arr sends 0 for an unknown year.
            year=int(year) if year.isdigit() and int(year) > 0 else None,
            slug=self.slug.strip(),
            original_language=normalise_language(self.original_language.strip()),
            tags=tuple(dict.fromkeys(t.strip().lower() for t in self.tags.split("|") if t.strip())),
        )


class ArrModel(WireModel):
    instance: str
    title: str
    year: int | None
    original_language: str | None
    tags: list[str] = Field(default_factory=list)
    # The movie or series in *arr, when it reported its own URL.
    link: str | None

    @classmethod
    def from_context(cls, app: App, context: ArrContext | None) -> ArrModel | None:
        if context is None:
            return None
        return cls(
            instance=context.instance,
            title=context.title,
            year=context.year,
            original_language=context.original_language,
            tags=list(context.tags),
            link=item_url(app, context),
        )
