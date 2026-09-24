#!/usr/bin/env python3
"""Render the per-app *arr shims from one template.

    python3 scripts/build_shims.py          # rewrite the shims
    python3 scripts/build_shims.py --check  # exit 1 if they are out of date

The shims are published as standalone files (users copy them into the *arr
container), so they are generated and committed rather than sourcing a library.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "src" / "muxarr-import.sh.in"
# Placeholder -> value per app. @slug@ names the variable holding the item's route in
# the *arr UI: Radarr's movie pages are keyed by TMDb id, Sonarr's by title slug.
APPS = {
    "radarr": {"@App@": "Radarr", "@app@": "radarr", "@item@": "movie", "@slug@": "tmdbid"},
    "sonarr": {"@App@": "Sonarr", "@app@": "sonarr", "@item@": "series", "@slug@": "titleslug"},
}


def render(app: str) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    for placeholder, value in APPS[app].items():
        text = text.replace(placeholder, value)
    return text


def target(app: str) -> Path:
    return HERE / f"muxarr-import-{app}.sh"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for app in APPS:
        path = target(app)
        wanted = render(app)
        if path.exists() and path.read_text(encoding="utf-8") == wanted:
            continue
        if check:
            stale.append(path.name)
            continue
        path.write_text(wanted, encoding="utf-8")
        path.chmod(0o755)
        print(f"wrote {path.relative_to(HERE.parent)}")

    if stale:
        print(f"out of date: {', '.join(stale)}; run python3 scripts/build_shims.py")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
