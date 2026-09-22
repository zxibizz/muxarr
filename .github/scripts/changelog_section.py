#!/usr/bin/env python3
"""Print the CHANGELOG.md section for one version, for use as release notes.

Usage:
    changelog_section.py v1.2.3
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def section(version: str) -> str:
    heading = f"## [{version}]"
    lines = (ROOT / "CHANGELOG.md").read_text().splitlines()

    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(heading))
    except StopIteration:
        raise SystemExit(f"no '{heading}' section in CHANGELOG.md") from None

    end = next(
        (i for i, line in enumerate(lines[start + 1 :], start + 1) if line.startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start + 1 : end]).strip()


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit("usage: changelog_section.py <tag>")
    print(section(argv[0].removeprefix("refs/tags/").removeprefix("v")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
