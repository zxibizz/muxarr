#!/usr/bin/env python3
"""Assert the three version mirrors agree, and optionally match a release tag.

The version is declared in three files because none of them can import the
others: the backend package, the frontend bundle and the Python distribution
metadata. This is the guard that keeps them from drifting.

Usage:
    check_version.py            # the three files agree
    check_version.py v1.2.3     # ...and match this git tag
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _match(path: Path, pattern: str) -> str:
    text = (ROOT / path).read_text()
    found = re.search(pattern, text, re.MULTILINE)
    if found is None:
        raise SystemExit(f"no version matching {pattern!r} in {path}")
    return found.group(1)


def from_pyproject() -> str:
    # Regex rather than tomllib so this runs under any python3, not just 3.11+.
    return _match(Path("services/backend/pyproject.toml"), r'^version = "([^"]+)"')


def from_init() -> str:
    return _match(Path("services/backend/src/__init__.py"), r'^__version__ = "([^"]+)"')


def from_package_json() -> str:
    data = json.loads((ROOT / "services/frontend/package.json").read_text())
    version = data["version"]
    assert isinstance(version, str)
    return version


def from_package_json() -> str:
    data = json.loads((ROOT / "services/frontend/package.json").read_text())
    version = data["version"]
    assert isinstance(version, str)
    return version


def main(argv: list[str]) -> int:
    found = {
        "services/backend/pyproject.toml": from_pyproject(),
        "services/backend/src/__init__.py": from_init(),
        "services/frontend/package.json": from_package_json(),
    }

    if argv:
        found["git tag"] = argv[0].removeprefix("refs/tags/").removeprefix("v")

    distinct = set(found.values())
    if len(distinct) == 1:
        print(f"version {distinct.pop()} is consistent across {len(found)} sources")
        return 0

    print("version mismatch:", file=sys.stderr)
    for source, version in found.items():
        print(f"  {version:<12} {source}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
